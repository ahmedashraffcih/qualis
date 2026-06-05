from __future__ import annotations

from typing import TYPE_CHECKING

from qualis.config.loader import load_rules_from_directory
from qualis.discover.suggester import RuleSuggestion
from qualis.discover.writer import suggestions_to_yaml, write_suggestions
from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.evidence import ProfileEvidence, SuggestionEvidence
from qualis.domain.models import Rule
from qualis.domain.params import InSetParams, NotNullParams

if TYPE_CHECKING:
    from pathlib import Path


def _suggestion(check: str, params: object, column: str = "col") -> RuleSuggestion:
    return RuleSuggestion(
        rule=Rule(
            id=f"DQ-{check.upper()}-{column}",
            name=f"{column} {check}",
            dimension=DQDimension.COMPLETENESS,
            rule_type=RuleType.AGGREGATE,
            severity=Severity.WARNING,
            dataset="accidents",
            column=column,
            check=check,
            params=params,  # type: ignore[arg-type]
        ),
        confidence="high",
        evidence=SuggestionEvidence(
            profile=ProfileEvidence(
                total_rows=10, null_count=0, null_fraction=0.0,
                distinct_count=10, distinct_fraction=1.0,
                min_value=None, max_value=None, top_values=[],
            ),
            heuristic=check,
            heuristic_reason="test",
        ),
    )


def test_yaml_contains_rules_key() -> None:
    s = [_suggestion("not_null", NotNullParams())]
    yaml_str = suggestions_to_yaml(s)
    assert "rules:" in yaml_str


def test_yaml_contains_rule_id() -> None:
    s = [_suggestion("not_null", NotNullParams())]
    yaml_str = suggestions_to_yaml(s)
    assert "DQ-NOT_NULL-col" in yaml_str


def test_yaml_in_set_parameters_serialized() -> None:
    s = [_suggestion("in_set", InSetParams(values=["A", "B"]))]
    yaml_str = suggestions_to_yaml(s)
    assert "values:" in yaml_str
    assert "A" in yaml_str and "B" in yaml_str


def test_write_round_trips_through_loader(tmp_path: Path) -> None:
    """Written YAML must be loadable by the rule loader — the round-trip is the contract."""
    suggestions = [
        _suggestion("not_null", NotNullParams(), column="email"),
        _suggestion("in_set", InSetParams(values=["A", "B"]), column="status"),
    ]
    out = tmp_path / "rules" / "discovered.yaml"
    write_suggestions(suggestions, out)
    rules = load_rules_from_directory(out.parent)
    assert len(rules) == 2
    assert rules[0].check == "not_null"
    assert rules[1].check == "in_set"
    assert isinstance(rules[1].params, InSetParams)
    assert rules[1].params.values == ["A", "B"]


# ---------------------------------------------------------------------------
# v0.3.0: status + metadata emission
# ---------------------------------------------------------------------------


def test_writer_emits_status_when_not_active() -> None:
    """status field is only emitted when it differs from the default (active)."""
    import yaml

    from qualis.discover.suggester import RuleSuggestion
    from qualis.discover.writer import suggestions_to_yaml
    from qualis.domain.enums import DQDimension, RuleStatus, RuleType, Severity
    from qualis.domain.evidence import ProfileEvidence, SuggestionEvidence
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r1", name="x",
        dimension=DQDimension.COMPLETENESS, rule_type=RuleType.AGGREGATE,
        severity=Severity.CRITICAL, dataset="d", column="c",
        check="not_null", params=NotNullParams(),
        status=RuleStatus.NEEDS_EVIDENCE,
    )
    profile = ProfileEvidence(
        total_rows=10, null_count=0, null_fraction=0.0,
        distinct_count=10, distinct_fraction=1.0,
        min_value=None, max_value=None, top_values=[],
    )
    suggestion = RuleSuggestion(
        rule=rule, confidence="high",
        evidence=SuggestionEvidence(
            profile=profile, heuristic="not_null", heuristic_reason="x",
        ),
    )
    out = yaml.safe_load(suggestions_to_yaml([suggestion]))
    assert out["rules"][0]["status"] == "needs_evidence"


def test_writer_omits_status_when_active() -> None:
    """Active is the default; emitting it would be noise."""
    import yaml

    from qualis.discover.suggester import RuleSuggestion
    from qualis.discover.writer import suggestions_to_yaml
    from qualis.domain.enums import DQDimension, RuleStatus, RuleType, Severity
    from qualis.domain.evidence import ProfileEvidence, SuggestionEvidence
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r1", name="x",
        dimension=DQDimension.COMPLETENESS, rule_type=RuleType.AGGREGATE,
        severity=Severity.CRITICAL, dataset="d", column="c",
        check="not_null", params=NotNullParams(),
        status=RuleStatus.ACTIVE,
    )
    profile = ProfileEvidence(
        total_rows=10, null_count=0, null_fraction=0.0,
        distinct_count=10, distinct_fraction=1.0,
        min_value=None, max_value=None, top_values=[],
    )
    suggestion = RuleSuggestion(
        rule=rule, confidence="high",
        evidence=SuggestionEvidence(
            profile=profile, heuristic="not_null", heuristic_reason="x",
        ),
    )
    out = yaml.safe_load(suggestions_to_yaml([suggestion]))
    assert "status" not in out["rules"][0]


def test_condition_round_trips() -> None:
    """AgDR-0005: writer preserves condition (it was silently dropped before)."""
    from qualis.discover.writer import _rule_to_dict
    from qualis.domain.enums import DQDimension, RuleType, Severity
    from qualis.domain.models import Rule
    from qualis.domain.params import NotNullParams

    rule = Rule(
        id="r1", name="x", dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.ROW_LEVEL, severity=Severity.CRITICAL,
        dataset="t", column="c", check="not_null", params=NotNullParams(),
        condition="status = 'active'",
    )
    out = _rule_to_dict(rule)
    assert out["condition"] == "status = 'active'"
