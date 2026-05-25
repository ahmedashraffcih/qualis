from __future__ import annotations

from typing import Any

import pytest

from qualis.adapters.in_memory.adapter import InMemoryAdapter


@pytest.fixture()
def adapter() -> InMemoryAdapter:
    """Adapter seeded with a 'public.users' table containing 4 rows."""
    a = InMemoryAdapter()
    rows: list[dict[str, Any]] = [
        {"id": "1", "email": "alice@example.com", "age": 25, "code": "A001"},
        {"id": "2", "email": None, "age": 200, "code": "B-INVALID"},
        {"id": "3", "email": "bob@example.com", "age": 30, "code": "A002"},
        {"id": "4", "email": "bob@example.com", "age": 30, "code": "C999"},
    ]
    a.add_table("public", "users", rows)
    return a


class TestTableExists:
    def test_existing_table(self, adapter: InMemoryAdapter) -> None:
        assert adapter.table_exists("public", "users") is True

    def test_missing_table(self, adapter: InMemoryAdapter) -> None:
        assert adapter.table_exists("public", "orders") is False

    def test_wrong_schema(self, adapter: InMemoryAdapter) -> None:
        assert adapter.table_exists("private", "users") is False


class TestQuery:
    def test_returns_all_rows(self, adapter: InMemoryAdapter) -> None:
        rows = adapter.query("SELECT * FROM public.users")
        assert len(rows) == 4

    def test_returns_list_of_dicts(self, adapter: InMemoryAdapter) -> None:
        rows = adapter.query("SELECT * FROM public.users")
        assert all(isinstance(r, dict) for r in rows)

    def test_unknown_table_returns_empty(self, adapter: InMemoryAdapter) -> None:
        rows = adapter.query("SELECT * FROM public.orders")
        assert rows == []

    def test_returns_copy_not_reference(self, adapter: InMemoryAdapter) -> None:
        rows1 = adapter.query("SELECT * FROM public.users")
        rows2 = adapter.query("SELECT * FROM public.users")
        assert rows1 is not rows2


class TestStream:
    def test_chunk_size_2_produces_2_chunks(self, adapter: InMemoryAdapter) -> None:
        chunks = list(adapter.stream("SELECT * FROM public.users", chunk_size=2))
        assert len(chunks) == 2

    def test_first_chunk_has_2_rows(self, adapter: InMemoryAdapter) -> None:
        chunks = list(adapter.stream("SELECT * FROM public.users", chunk_size=2))
        assert len(chunks[0]) == 2

    def test_second_chunk_has_2_rows(self, adapter: InMemoryAdapter) -> None:
        chunks = list(adapter.stream("SELECT * FROM public.users", chunk_size=2))
        assert len(chunks[1]) == 2

    def test_chunk_size_3_last_chunk_partial(self, adapter: InMemoryAdapter) -> None:
        chunks = list(adapter.stream("SELECT * FROM public.users", chunk_size=3))
        assert len(chunks) == 2
        assert len(chunks[0]) == 3
        assert len(chunks[1]) == 1

    def test_all_rows_covered(self, adapter: InMemoryAdapter) -> None:
        chunks = list(adapter.stream("SELECT * FROM public.users", chunk_size=2))
        all_rows = [r for chunk in chunks for r in chunk]
        assert len(all_rows) == 4

    def test_unknown_table_yields_nothing(self, adapter: InMemoryAdapter) -> None:
        chunks = list(adapter.stream("SELECT * FROM public.missing", chunk_size=2))
        assert chunks == []

    def test_chunk_size_larger_than_table(self, adapter: InMemoryAdapter) -> None:
        chunks = list(adapter.stream("SELECT * FROM public.users", chunk_size=100))
        assert len(chunks) == 1
        assert len(chunks[0]) == 4


class TestCheckNotNull:
    def test_finds_one_null(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_not_null("public", "users", "email")
        assert result["null_count"] == 1

    def test_total_count(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_not_null("public", "users", "email")
        assert result["total_count"] == 4

    def test_no_nulls_in_id_column(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_not_null("public", "users", "id")
        assert result["null_count"] == 0

    def test_missing_table_raises(self, adapter: InMemoryAdapter) -> None:
        with pytest.raises(ValueError, match=r"public\.missing not found"):
            adapter.check_not_null("public", "missing", "email")


class TestCheckUnique:
    def test_finds_duplicate_email(self, adapter: InMemoryAdapter) -> None:
        # "bob@example.com" appears twice
        result = adapter.check_unique("public", "users", "email")
        assert result["duplicate_count"] == 1

    def test_total_count(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_unique("public", "users", "email")
        assert result["total_count"] == 4

    def test_id_column_all_unique(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_unique("public", "users", "id")
        assert result["duplicate_count"] == 0


class TestCheckBetween:
    def test_finds_out_of_range_code(self, adapter: InMemoryAdapter) -> None:
        # code values: A001, B-INVALID, A002, C999
        # between "A001".."A999" — A001 and A002 in range; B-INVALID and C999 out
        result = adapter.check_between("public", "users", "code", "A001", "A999")
        assert result["out_of_range_count"] == 2

    def test_total_count(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_between("public", "users", "code", "A001", "A999")
        assert result["total_count"] == 4

    def test_checked_excludes_nulls(self, adapter: InMemoryAdapter) -> None:
        # email column has 1 null; checking email between "a" and "z"
        result = adapter.check_between("public", "users", "email", "a", "z")
        assert result["checked"] == 3  # row with None email skipped

    def test_all_in_range(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_between("public", "users", "code", "A", "Z")
        assert result["out_of_range_count"] == 0


class TestCheckRegex:
    def test_finds_non_matching_codes(self, adapter: InMemoryAdapter) -> None:
        # pattern expects A or B prefix; "C999" and "B-INVALID" (no digit after B)
        # more precisely: pattern r"^[AB]\d{3}$" matches A001, A002 but not B-INVALID, C999
        result = adapter.check_regex("public", "users", "code", r"^[AB]\d{3}$")
        assert result["non_matching_count"] == 2

    def test_total_count(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_regex("public", "users", "code", r"^[AB]\d{3}$")
        assert result["total_count"] == 4

    def test_all_match(self, adapter: InMemoryAdapter) -> None:
        result = adapter.check_regex("public", "users", "id", r"^\d+$")
        assert result["non_matching_count"] == 0

    def test_null_values_count_as_non_matching(self, adapter: InMemoryAdapter) -> None:
        # email has 1 null; it should be counted as non-matching
        result = adapter.check_regex("public", "users", "email", r"^.+@.+\..+$")
        # row 2 (null), row 4 (duplicate but valid): only null fails
        assert result["non_matching_count"] == 1


class TestAddTable:
    def test_overwrites_existing_table(self) -> None:
        a = InMemoryAdapter()
        a.add_table("s", "t", [{"x": 1}])
        a.add_table("s", "t", [{"x": 2}, {"x": 3}])
        result = adapter_query_all(a, "s", "t")
        assert len(result) == 2

    def test_multiple_tables(self) -> None:
        a = InMemoryAdapter()
        a.add_table("s", "t1", [{"x": 1}])
        a.add_table("s", "t2", [{"y": 1}, {"y": 2}])
        assert a.table_exists("s", "t1")
        assert a.table_exists("s", "t2")


def adapter_query_all(a: InMemoryAdapter, schema: str, table: str) -> list[dict[str, Any]]:
    return a.query(f"SELECT * FROM {schema}.{table}")
