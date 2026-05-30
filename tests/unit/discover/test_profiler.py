from __future__ import annotations

from pathlib import Path

import pytest

from qualis.adapters.duckdb.adapter import DuckDBAdapter
from qualis.discover.profiler import profile_table

CSV_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "examples"
    / "traffic_safety"
    / "data"
    / "accidents.csv"
)


@pytest.fixture()
def adapter() -> DuckDBAdapter:
    a = DuckDBAdapter()
    a.register_csv("accidents", str(CSV_PATH))
    return a


def test_row_count_is_eleven(adapter: DuckDBAdapter) -> None:
    profile = profile_table(adapter, "accidents")
    assert profile.row_count == 11


def test_columns_are_discovered(adapter: DuckDBAdapter) -> None:
    profile = profile_table(adapter, "accidents")
    names = {c.name for c in profile.columns}
    assert {"id", "accident_date", "severity_code", "location_id"}.issubset(names)


def test_null_detection_for_accident_date(adapter: DuckDBAdapter) -> None:
    profile = profile_table(adapter, "accidents")
    accident_date = next(c for c in profile.columns if c.name == "accident_date")
    # The example data has 1 null in accident_date
    assert accident_date.null_count == 1


def test_distinct_count_for_severity(adapter: DuckDBAdapter) -> None:
    profile = profile_table(adapter, "accidents")
    severity = next(c for c in profile.columns if c.name == "severity_code")
    # FATAL, SERIOUS, MINOR, PROPERTY, INVALID — 5 distinct values
    assert severity.distinct_count == 5


def test_id_column_likely_id(adapter: DuckDBAdapter) -> None:
    profile = profile_table(adapter, "accidents")
    id_col = next(c for c in profile.columns if c.name == "id")
    assert id_col.is_likely_id is True


def test_min_max_for_severity(adapter: DuckDBAdapter) -> None:
    profile = profile_table(adapter, "accidents")
    severity = next(c for c in profile.columns if c.name == "severity_code")
    assert severity.min_value is not None
    assert severity.max_value is not None
