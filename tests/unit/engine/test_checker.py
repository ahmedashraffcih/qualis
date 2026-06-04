from __future__ import annotations

from pathlib import Path

from qualis.adapters.in_memory.adapter import InMemoryAdapter
from qualis.config.loader import load_rules_from_file
from qualis.domain.enums import DQDimension
from qualis.engine.checker import CheckRunner

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
COMPLETENESS_YAML = FIXTURES_DIR / "rules" / "completeness.yaml"

_SAMPLE_ROWS = [
    {"accident_date": "2024-01-15", "severity_code": "FATAL", "location_id": "101"},
    {"accident_date": None, "severity_code": "SERIOUS", "location_id": "102"},
    {"accident_date": "2024-03-20", "severity_code": "MINOR", "location_id": "103"},
]

_WEIGHTS: dict[DQDimension, float] = {
    DQDimension.COMPLETENESS: 1.0,
    DQDimension.VALIDITY: 1.0,
}


def _make_runner(redact: bool = False) -> CheckRunner:
    adapter = InMemoryAdapter()
    adapter.add_table("", "accidents", _SAMPLE_ROWS)
    rules = load_rules_from_file(COMPLETENESS_YAML)
    return CheckRunner(adapter, rules, _WEIGHTS, schema="", redact=redact)


def test_run_produces_dataset_score_with_correct_dataset_name() -> None:
    score = _make_runner().run()
    assert score.dataset == "accidents"


def test_aggregate_score_is_between_0_and_1() -> None:
    score = _make_runner().run()
    assert 0.0 <= score.aggregate_score <= 1.0


def test_dimension_scores_has_at_least_one_entry() -> None:
    score = _make_runner().run()
    assert len(score.dimension_scores) >= 1


def test_total_violations_is_non_negative() -> None:
    score = _make_runner().run()
    assert score.total_violations >= 0


def test_critical_violations_does_not_exceed_total_violations() -> None:
    score = _make_runner().run()
    assert score.critical_violations <= score.total_violations


def test_redact_flag_replaces_actual_value() -> None:
    """When redact=True every sampled violation's actual_value is [REDACTED]."""
    _, results = _make_runner(redact=True).run_detailed()
    sampled = [v for r in results for v in r.violations]
    assert sampled, "expected at least one sampled violation from the fixture"
    for v in sampled:
        assert v.actual_value == "[REDACTED]"


def test_redaction_is_immutable_and_bounded() -> None:
    """Redaction rebuilds frozen instances; originals are never mutated."""
    from qualis.domain.models import MAX_SAMPLE_VIOLATIONS, CheckResult, Violation
    from qualis.domain.rule_engine import RuleEngine

    adapter = InMemoryAdapter()
    adapter.add_table("", "accidents", _SAMPLE_ROWS)
    rules = load_rules_from_file(COMPLETENESS_YAML)
    engine = RuleEngine(adapter, "")
    original = next(r for r in engine.evaluate_all(rules) if r.violations)
    pre_redaction_value = original.violations[0].actual_value

    redacted = CheckRunner._redact_result(original)

    # New frozen instances — the originals are untouched.
    assert redacted is not original
    assert redacted.violations[0] is not original.violations[0]
    assert isinstance(redacted, CheckResult)
    assert isinstance(redacted.violations[0], Violation)
    assert original.violations[0].actual_value == pre_redaction_value
    assert redacted.violations[0].actual_value == "[REDACTED]"
    # Counts and bound preserved.
    assert redacted.violation_count == original.violation_count
    assert len(redacted.violations) <= MAX_SAMPLE_VIOLATIONS


def test_redact_result_passthrough_when_no_violations() -> None:
    """Results with no sampled violations are returned unchanged."""
    from qualis.domain.rule_engine import RuleEngine

    adapter = InMemoryAdapter()
    adapter.add_table("", "accidents", _SAMPLE_ROWS)
    rules = load_rules_from_file(COMPLETENESS_YAML)
    engine = RuleEngine(adapter, "")
    clean = next(r for r in engine.evaluate_all(rules) if not r.violations)

    assert CheckRunner._redact_result(clean) is clean
