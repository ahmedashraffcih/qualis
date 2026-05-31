from __future__ import annotations

from qualis.discover.profiler import ColumnProfile, TableProfile
from qualis.discover.suggester import suggest_rules
from qualis.domain.enums import DQDimension
from qualis.domain.params import (
    BetweenParams,
    InSetParams,
    NotNegativeParams,
    NotNullParams,
    UniqueParams,
)


def _col(**overrides: object) -> ColumnProfile:
    defaults: dict[str, object] = {
        "name": "x",
        "inferred_type": "string",
        "total_count": 100,
        "null_count": 0,
        "null_fraction": 0.0,
        "distinct_count": 50,
        "distinct_fraction": 0.5,
        "min_value": "a",
        "max_value": "z",
        "sample_values": [],
        "is_likely_id": False,
    }
    defaults.update(overrides)
    return ColumnProfile(**defaults)  # type: ignore[arg-type]


def _profile(cols: list[ColumnProfile]) -> TableProfile:
    return TableProfile(table="t", row_count=100, columns=cols)


def test_not_null_suggested_for_zero_null_column() -> None:
    cols = [_col(name="email", null_count=0, total_count=10)]
    suggestions = suggest_rules(_profile(cols))
    not_null = [s for s in suggestions if s.rule.check == "not_null"]
    assert len(not_null) == 1
    assert isinstance(not_null[0].rule.params, NotNullParams)
    assert not_null[0].confidence == "high"


def test_not_null_severity_is_warning_for_non_id_column() -> None:
    from qualis.domain.enums import Severity
    cols = [_col(name="email", null_count=0, total_count=10)]
    suggestions = suggest_rules(_profile(cols))
    not_null = next(s for s in suggestions if s.rule.check == "not_null")
    assert not_null.rule.severity == Severity.WARNING


def test_not_null_severity_is_critical_for_id_column() -> None:
    from qualis.domain.enums import Severity
    cols = [_col(name="user_id", null_count=0, is_likely_id=True, distinct_count=100)]
    suggestions = suggest_rules(_profile(cols))
    not_null = next(s for s in suggestions if s.rule.check == "not_null")
    assert not_null.rule.severity == Severity.CRITICAL


def test_unique_suggested_for_id_column() -> None:
    cols = [_col(name="user_id", is_likely_id=True, distinct_count=100)]
    suggestions = suggest_rules(_profile(cols))
    unique = [s for s in suggestions if s.rule.check == "unique"]
    assert len(unique) == 1
    assert isinstance(unique[0].rule.params, UniqueParams)
    assert unique[0].confidence == "high"


def test_unique_severity_is_critical_for_named_id_column() -> None:
    from qualis.domain.enums import Severity
    cols = [_col(name="user_id", is_likely_id=True, distinct_count=100)]
    suggestions = suggest_rules(_profile(cols))
    unique = next(s for s in suggestions if s.rule.check == "unique")
    assert unique.rule.severity == Severity.CRITICAL


def test_in_set_suggested_for_low_cardinality_string() -> None:
    cols = [
        _col(
            name="status",
            inferred_type="string",
            distinct_count=3,
            sample_values=["A", "B", "C"],
        )
    ]
    suggestions = suggest_rules(_profile(cols))
    in_set = [s for s in suggestions if s.rule.check == "in_set"]
    assert len(in_set) == 1
    assert isinstance(in_set[0].rule.params, InSetParams)
    assert in_set[0].rule.params.values == ["A", "B", "C"]


def test_in_set_confidence_is_medium_not_high() -> None:
    """in_set is medium-confidence: we only see observed values, not the
    authoritative valid domain. High would be epistemically wrong."""
    cols = [
        _col(
            name="status",
            inferred_type="string",
            distinct_count=3,
            sample_values=["A", "B", "C"],
        )
    ]
    in_set = next(s for s in suggest_rules(_profile(cols)) if s.rule.check == "in_set")
    assert in_set.confidence == "medium"


def test_in_set_rationale_warns_to_verify_against_source_of_truth() -> None:
    cols = [
        _col(
            name="status",
            inferred_type="string",
            distinct_count=3,
            sample_values=["A", "B", "C"],
        )
    ]
    in_set = next(s for s in suggest_rules(_profile(cols)) if s.rule.check == "in_set")
    assert "verify" in in_set.rationale.lower()
    assert "authoritative" in in_set.rationale.lower()


def test_between_suggested_for_numeric_column() -> None:
    cols = [
        _col(
            name="age",
            inferred_type="integer",
            min_value="0",
            max_value="120",
            distinct_count=80,
        )
    ]
    suggestions = suggest_rules(_profile(cols))
    between = [s for s in suggestions if s.rule.check == "between"]
    assert len(between) == 1
    assert isinstance(between[0].rule.params, BetweenParams)
    assert between[0].rule.params.min == "0"
    assert between[0].rule.params.max == "120"


def test_not_negative_suggested_for_positive_numeric() -> None:
    cols = [_col(name="amount", inferred_type="integer", min_value="5", max_value="1000")]
    suggestions = suggest_rules(_profile(cols))
    not_neg = [s for s in suggestions if s.rule.check == "not_negative"]
    assert len(not_neg) == 1
    assert isinstance(not_neg[0].rule.params, NotNegativeParams)


def test_dimension_assignment() -> None:
    cols = [
        _col(
            name="id",
            null_count=0,
            is_likely_id=True,
            inferred_type="integer",
            min_value="1",
            max_value="100",
        ),
    ]
    suggestions = suggest_rules(_profile(cols))
    dims = {s.rule.dimension for s in suggestions}
    assert DQDimension.COMPLETENESS in dims  # not_null
    assert DQDimension.UNIQUENESS in dims    # unique


def test_no_suggestions_for_empty_profile() -> None:
    assert suggest_rules(_profile([])) == []
