from __future__ import annotations

from pathlib import Path

import pytest

from qualis.adapters.duckdb.adapter import DuckDBAdapter

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "data"
CSV_PATH = str(FIXTURES_DIR / "accidents.csv")


@pytest.fixture()
def adapter() -> DuckDBAdapter:
    """In-memory DuckDBAdapter with the accidents CSV registered."""
    adp = DuckDBAdapter()
    adp.register_csv("accidents", CSV_PATH)
    return adp


def test_query_returns_all_rows(adapter: DuckDBAdapter) -> None:
    rows = adapter.query('SELECT * FROM "accidents"')
    assert len(rows) == 6


def test_query_returns_dicts_with_column_names(adapter: DuckDBAdapter) -> None:
    rows = adapter.query('SELECT * FROM "accidents"')
    assert isinstance(rows[0], dict)
    expected_columns = {"id", "accident_date", "severity_code", "location_id", "report_date"}
    assert expected_columns.issubset(set(rows[0].keys()))


def test_check_not_null_finds_one_null_in_accident_date(adapter: DuckDBAdapter) -> None:
    result = adapter.check_not_null("", "accidents", "accident_date")
    assert result["null_count"] == 1
    assert result["total_count"] == 6


def test_check_not_null_finds_zero_nulls_in_severity_code(adapter: DuckDBAdapter) -> None:
    result = adapter.check_not_null("", "accidents", "severity_code")
    assert result["null_count"] == 0
    assert result["total_count"] == 6


def test_check_unique_finds_duplicates_in_id(adapter: DuckDBAdapter) -> None:
    result = adapter.check_unique("", "accidents", "id")
    # id=1 appears twice; one group of duplicates
    assert result["duplicate_count"] >= 1
    assert result["total_count"] == 6


def test_check_between_dates_in_2024_range(adapter: DuckDBAdapter) -> None:
    result = adapter.check_between("", "accidents", "accident_date", "2024-01-01", "2024-12-31")
    # All non-null dates fall within 2024; NULL is not counted as out-of-range
    assert result["out_of_range_count"] == 0
    assert result["total_count"] == 6


def test_check_regex_finds_invalid_severity_code(adapter: DuckDBAdapter) -> None:
    result = adapter.check_regex("", "accidents", "severity_code", "FATAL|SERIOUS|MINOR|PROPERTY")
    # "INVALID" does not match the pattern
    assert result["non_matching_count"] == 1
    assert result["total_count"] == 6


def test_table_exists_for_registered_table(adapter: DuckDBAdapter) -> None:
    assert adapter.table_exists("", "accidents") is True


def test_table_exists_returns_false_for_missing_table(adapter: DuckDBAdapter) -> None:
    assert adapter.table_exists("", "nonexistent_table") is False


def test_check_in_set_finds_invalid_severity(adapter: DuckDBAdapter) -> None:
    result = adapter.check_in_set(
        "", "accidents", "severity_code",
        ["FATAL", "SERIOUS", "MINOR", "PROPERTY"],
    )
    # "INVALID" is not in the allowed set
    assert result["invalid_count"] == 1
    assert result["total_count"] == 6


def test_check_in_set_all_valid(adapter: DuckDBAdapter) -> None:
    result = adapter.check_in_set(
        "", "accidents", "severity_code",
        ["FATAL", "SERIOUS", "MINOR", "PROPERTY", "INVALID"],
    )
    assert result["invalid_count"] == 0


def test_check_row_count(adapter: DuckDBAdapter) -> None:
    result = adapter.check_row_count("", "accidents")
    assert result["row_count"] == 6


def test_check_not_negative_on_positive_ids(adapter: DuckDBAdapter) -> None:
    result = adapter.check_not_negative("", "accidents", "id")
    assert result["negative_count"] == 0
    assert result["total_count"] == 6


def test_check_reference_lookup_finds_invalid(adapter: DuckDBAdapter) -> None:
    # severity_code in the fixture has FATAL/SERIOUS/INVALID/MINOR/FATAL/PROPERTY.
    # Restrict valid set to FATAL/SERIOUS/MINOR/PROPERTY — flags INVALID.
    result = adapter.check_reference_lookup(
        "", "accidents", "severity_code",
        valid_values=["FATAL", "SERIOUS", "MINOR", "PROPERTY"],
    )
    assert result["invalid_count"] == 1
    assert result["total_count"] == 6


def test_check_reference_lookup_all_valid(adapter: DuckDBAdapter) -> None:
    result = adapter.check_reference_lookup(
        "", "accidents", "severity_code",
        valid_values=["FATAL", "SERIOUS", "MINOR", "PROPERTY", "INVALID"],
    )
    assert result["invalid_count"] == 0


class TestFetchViolationSamples:
    """Optional sampling capability: real failing rows as evidence."""

    def test_in_set_returns_invalid_value_with_rid(self, adapter: DuckDBAdapter) -> None:
        samples = adapter.fetch_violation_samples(
            "", "accidents", "severity_code", "in_set",
            {"values": ["FATAL", "SERIOUS", "MINOR", "PROPERTY"]}, 10,
        )
        assert len(samples) == 1
        assert samples[0]["actual_value"] == "INVALID"
        assert samples[0]["record_id"] is not None

    def test_not_null_returns_null_row(self, adapter: DuckDBAdapter) -> None:
        samples = adapter.fetch_violation_samples(
            "", "accidents", "accident_date", "not_null", {}, 10,
        )
        assert len(samples) == 1
        assert samples[0]["actual_value"] is None

    def test_unique_returns_duplicated_rows_capped(self, adapter: DuckDBAdapter) -> None:
        samples = adapter.fetch_violation_samples(
            "", "accidents", "id", "unique", {}, 1,
        )
        assert len(samples) == 1  # limit respected
        assert samples[0]["actual_value"] == 1

    def test_unsupported_kind_raises(self, adapter: DuckDBAdapter) -> None:
        with pytest.raises(ValueError, match="unsupported sample kind"):
            adapter.fetch_violation_samples("", "accidents", "id", "row_count", {}, 5)


class TestConditions:
    """Condition pushdown (AgDR-0005) via the literal-style SQL renderer."""

    def test_supports_conditions_flag(self, adapter: DuckDBAdapter) -> None:
        assert adapter.supports_conditions is True

    def test_condition_filters_population(self, adapter: DuckDBAdapter) -> None:
        from qualis.domain.condition import parse_condition

        cond = parse_condition("severity_code = 'FATAL'")
        result = adapter.check_not_null("", "accidents", "accident_date", condition=cond)
        assert result == {"null_count": 0, "total_count": 2}

    def test_unique_condition_applies_to_inner_scan(self, adapter: DuckDBAdapter) -> None:
        from qualis.domain.condition import parse_condition

        # id=1 duplicates across FATAL+PROPERTY; FATAL-only population has one
        cond = parse_condition("severity_code = 'FATAL'")
        result = adapter.check_unique("", "accidents", "id", condition=cond)
        assert result["duplicate_count"] == 0
        assert result["total_count"] == 2

    def test_conditioned_samples_respect_population(self, adapter: DuckDBAdapter) -> None:
        from qualis.domain.condition import parse_condition

        cond = parse_condition("severity_code != 'SERIOUS'")
        samples = adapter.fetch_violation_samples(
            "", "accidents", "accident_date", "not_null", {}, 10, condition=cond,
        )
        assert samples == []  # the only null date is on the SERIOUS row


class TestReferenceJoin:
    """AgDR-0006 JOIN-mode lookup on duckdb (C1 + C2 proofs)."""

    @pytest.fixture()
    def ref_adapter(self) -> DuckDBAdapter:
        a = DuckDBAdapter()
        a._con.execute("CREATE TABLE orders (id INTEGER, country TEXT, region TEXT)")
        a._con.execute(
            "INSERT INTO orders VALUES (1,'US','amer'),(2,'GB','emea'),"
            "(3,'XX','emea'),(4,NULL,'apac')"
        )
        a._con.execute("CREATE TABLE countries (code TEXT, region TEXT)")
        a._con.execute("INSERT INTO countries VALUES ('US','amer'),('GB','emea'),(NULL,'x')")
        return a

    def test_null_ref_key_does_not_zero_invalid_count(self, ref_adapter: DuckDBAdapter) -> None:
        result = ref_adapter.check_reference_join(
            "", "orders", "country", "", "countries", "code"
        )
        assert result == {"invalid_count": 1, "total_count": 4}

    def test_condition_with_colliding_column_name(self, ref_adapter: DuckDBAdapter) -> None:
        from qualis.domain.condition import parse_condition

        result = ref_adapter.check_reference_join(
            "", "orders", "country", "", "countries", "code",
            condition=parse_condition("region = 'emea'"),
        )
        assert result == {"invalid_count": 1, "total_count": 2}

    def test_join_sampling(self, ref_adapter: DuckDBAdapter) -> None:
        samples = ref_adapter.fetch_violation_samples(
            "", "orders", "country", "reference_join",
            {"reference_schema": "", "reference": "countries", "key_column": "code"},
            10,
        )
        assert [s["actual_value"] for s in samples] == ["XX"]


def test_reference_join_same_column_name_no_tautology() -> None:
    """Parity regression with the sqlalchemy same-name fix."""
    a = DuckDBAdapter()
    a._con.execute("CREATE TABLE t (code TEXT)")
    a._con.execute("INSERT INTO t VALUES ('XX')")
    a._con.execute("CREATE TABLE ref (code TEXT)")
    a._con.execute("INSERT INTO ref VALUES ('US')")
    result = a.check_reference_join("", "t", "code", "", "ref", "code")
    assert result == {"invalid_count": 1, "total_count": 1}


class TestCheckAggregate:
    """cross_dataset_assertion capability (AgDR-0008)."""

    def _adp(self) -> DuckDBAdapter:
        a = DuckDBAdapter()
        a._con.execute(
            "CREATE TABLE t (amount DOUBLE); "
            "INSERT INTO t VALUES (1.5), (2.5), (NULL)"
        )
        a._con.execute("CREATE TABLE empty_t (amount DOUBLE)")
        return a

    def test_row_count(self) -> None:
        a = self._adp()
        assert a.check_aggregate("", "t", "row_count")["value"] == 3

    def test_sum_excludes_nulls(self) -> None:
        a = self._adp()
        assert float(a.check_aggregate("", "t", "sum", "amount")["value"]) == 4.0

    def test_sum_of_empty_table_is_zero_not_null(self) -> None:
        a = self._adp()
        value = a.check_aggregate("", "empty_t", "sum", "amount")["value"]
        assert value is not None
        assert float(value) == 0.0

    def test_unknown_metric_rejected(self) -> None:
        a = self._adp()
        with pytest.raises(ValueError, match="unsupported metric"):
            a.check_aggregate("", "t", "count_distinct", "amount")

    def test_sum_without_column_rejected(self) -> None:
        a = self._adp()
        with pytest.raises(ValueError, match="column"):
            a.check_aggregate("", "t", "sum")
