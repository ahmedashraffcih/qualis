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


def test_numeric_min_max_sorts_numerically_not_lexicographically(
    tmp_path: Path,
) -> None:
    """Regression: MIN/MAX on numeric columns must not use VARCHAR ordering.

    Before the fix, an int column with values 1, 2, 10, 99, 500 reported
    max='99' because the profiler cast to VARCHAR before MIN/MAX. This
    produced silently-wrong `between` rule bounds at discovery time.
    """
    csv = tmp_path / "numeric.csv"
    csv.write_text("order_id,amount\n1,100\n2,250\n10,75\n99,500\n500,30\n")
    a = DuckDBAdapter()
    a.register_csv("numeric", str(csv))
    profile = profile_table(a, "numeric")
    order_id = next(c for c in profile.columns if c.name == "order_id")
    assert order_id.inferred_type == "integer"
    # Lexically '99' > '500'. Numerically 500 > 99.
    assert order_id.max_value == "500"
    assert order_id.min_value == "1"
    amount = next(c for c in profile.columns if c.name == "amount")
    assert amount.max_value == "500"
    assert amount.min_value == "30"
