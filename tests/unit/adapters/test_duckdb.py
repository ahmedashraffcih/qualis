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
