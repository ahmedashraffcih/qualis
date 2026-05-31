from __future__ import annotations

from qualis.discover.evidence_builder import build_profile_evidence
from qualis.discover.profiler import ColumnProfile


def _col(**overrides: object) -> ColumnProfile:
    defaults: dict[str, object] = {
        "name": "x",
        "inferred_type": "string",
        "total_count": 100,
        "null_count": 0,
        "null_fraction": 0.0,
        "distinct_count": 4,
        "distinct_fraction": 0.04,
        "min_value": "A",
        "max_value": "D",
        "sample_values": ["A", "B", "C", "D"],
        "is_likely_id": False,
    }
    defaults.update(overrides)
    return ColumnProfile(**defaults)  # type: ignore[arg-type]


def test_profile_evidence_carries_basic_stats() -> None:
    col = _col(total_count=1000, null_count=5, distinct_count=10)
    ev = build_profile_evidence(col, top_values=[])
    assert ev.total_rows == 1000
    assert ev.null_count == 5
    assert ev.distinct_count == 10


def test_profile_evidence_carries_min_max() -> None:
    col = _col(min_value="2020-01-01", max_value="2026-12-31")
    ev = build_profile_evidence(col, top_values=[])
    assert ev.min_value == "2020-01-01"
    assert ev.max_value == "2026-12-31"


def test_profile_evidence_carries_top_values() -> None:
    col = _col()
    top = [("MINOR", 700), ("SERIOUS", 200), ("FATAL", 80), ("PROPERTY", 20)]
    ev = build_profile_evidence(col, top_values=top)
    assert ev.top_values == top


def test_null_fraction_passed_through() -> None:
    col = _col(total_count=100, null_count=5, null_fraction=0.05)
    ev = build_profile_evidence(col, top_values=[])
    assert ev.null_fraction == 0.05
