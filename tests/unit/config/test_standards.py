from __future__ import annotations

from qualis.config.standards import StandardsValidator
from qualis.domain.enums import DQDimension, RuleType, Severity
from qualis.domain.models import Rule
from qualis.domain.params import NotNullParams
from qualis.domain.standards import RuleMetadataSchema, StandardField


def _rule(metadata: dict[str, object] | None = None) -> Rule:
    return Rule(
        id="r", name="r",
        dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.AGGREGATE,
        severity=Severity.CRITICAL,
        dataset="d", column="c", check="not_null", params=NotNullParams(),
        metadata=metadata or {},
    )


def test_empty_schema_validates_everything() -> None:
    v = StandardsValidator(schema=RuleMetadataSchema())
    issues = v.validate(_rule())
    assert issues == []


def test_missing_required_field_reports_issue() -> None:
    v = StandardsValidator(schema=RuleMetadataSchema(
        fields=[StandardField(name="owner", required=True)],
    ))
    issues = v.validate(_rule())
    assert len(issues) == 1
    assert "owner" in issues[0]
    assert "missing" in issues[0].lower()


def test_present_required_field_passes() -> None:
    v = StandardsValidator(schema=RuleMetadataSchema(
        fields=[StandardField(name="owner", required=True)],
    ))
    issues = v.validate(_rule(metadata={"owner": "data-team"}))
    assert issues == []


def test_disallowed_value_reports_issue() -> None:
    v = StandardsValidator(schema=RuleMetadataSchema(
        fields=[StandardField(
            name="frequency",
            allowed_values=["hourly", "daily", "weekly"],
        )],
    ))
    issues = v.validate(_rule(metadata={"frequency": "monthly"}))
    assert len(issues) == 1
    assert "frequency" in issues[0]
    assert "monthly" in issues[0]


def test_allowed_value_passes() -> None:
    v = StandardsValidator(schema=RuleMetadataSchema(
        fields=[StandardField(
            name="frequency",
            allowed_values=["hourly", "daily", "weekly"],
        )],
    ))
    issues = v.validate(_rule(metadata={"frequency": "daily"}))
    assert issues == []


def test_optional_field_absent_passes() -> None:
    v = StandardsValidator(schema=RuleMetadataSchema(
        fields=[StandardField(name="glossary_term", required=False)],
    ))
    issues = v.validate(_rule())
    assert issues == []


def test_multiple_issues_all_reported() -> None:
    v = StandardsValidator(schema=RuleMetadataSchema(
        fields=[
            StandardField(name="owner", required=True),
            StandardField(name="cde", required=True),
        ],
    ))
    issues = v.validate(_rule())
    assert len(issues) == 2
