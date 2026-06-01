from __future__ import annotations

import difflib
import os
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import yaml

from qualis.domain.enums import CheckType, DQDimension, RuleStatus, RuleType, Severity
from qualis.domain.models import Rule
from qualis.domain.params import (
    BetweenParams,
    CheckParams,
    CustomParams,
    InSetParams,
    NotNegativeParams,
    NotNullParams,
    ReferenceLookupParams,
    RegexParams,
    RowCountParams,
    SqlParams,
    UniqueParams,
)

_TEMPLATE_VARS: dict[str, str] = {}


def _resolve_template_vars(value: str) -> str:
    """Resolve ``{{ variable }}`` template expressions in a string value."""
    today = date.today().isoformat()
    yesterday = date.fromordinal(date.today().toordinal() - 1).isoformat()
    now = datetime.now().isoformat(timespec="seconds")

    builtins: dict[str, str] = {
        "today": today,
        "yesterday": yesterday,
        "now": now,
    }

    result = value
    import re

    for match in re.finditer(r"\{\{\s*(\S+?)\s*\}\}", value):
        placeholder = match.group(0)
        key = match.group(1)

        if key.startswith("env."):
            env_var = key[4:]
            resolved = os.environ.get(env_var, "")
        else:
            resolved = builtins.get(key, placeholder)

        result = result.replace(placeholder, resolved)

    return result


def _fuzzy_validate(value: str, valid_values: list[str], field_name: str) -> str:
    """Return *value* if it is in *valid_values*; otherwise raise ValueError with suggestions."""
    if value in valid_values:
        return value

    suggestions = difflib.get_close_matches(value, valid_values, n=3, cutoff=0.6)
    suggestion_str = f"  Did you mean: {suggestions}" if suggestions else ""
    raise ValueError(
        f"Invalid {field_name} '{value}'. "
        f"Valid values are: {valid_values}.{suggestion_str}"
    )


def _parse_params(check: str, parameters: dict[str, Any] | None) -> CheckParams:
    """Build the appropriate ``CheckParams`` object for *check*."""
    params = parameters or {}
    if check == CheckType.NOT_NULL:
        return NotNullParams()
    if check == CheckType.UNIQUE:
        return UniqueParams()
    if check == CheckType.BETWEEN:
        min_raw = str(params.get("min", ""))
        max_raw = str(params.get("max", ""))
        return BetweenParams(
            min=_resolve_template_vars(min_raw),
            max=_resolve_template_vars(max_raw),
        )
    if check == CheckType.REGEX:
        return RegexParams(pattern=str(params.get("pattern", "")))
    if check == CheckType.SQL:
        return SqlParams(expression=str(params.get("expression", "")))
    if check == CheckType.CUSTOM:
        return CustomParams(handler=str(params.get("handler", "")))
    if check == CheckType.IN_SET:
        raw_values = params.get("values", [])
        return InSetParams(values=[str(v) for v in raw_values])
    if check == CheckType.ROW_COUNT:
        raw_min = params.get("min")
        raw_max = params.get("max")
        return RowCountParams(
            min=int(raw_min) if raw_min is not None else None,
            max=int(raw_max) if raw_max is not None else None,
        )
    if check == CheckType.NOT_NEGATIVE:
        return NotNegativeParams()
    if check == CheckType.REFERENCE_LOOKUP:
        return ReferenceLookupParams(
            reference=str(params.get("reference", "")),
            key_column=str(params.get("key_column", "")),
        )
    # Unreachable — check has already been validated against CheckType values
    raise ValueError(f"Unhandled check type: {check}")  # pragma: no cover


def _parse_rule(data: dict[str, Any]) -> Rule:
    """Parse a single rule dictionary from YAML into a ``Rule`` object."""
    valid_dimensions = [d.value for d in DQDimension]
    valid_severities = [s.value for s in Severity]
    valid_checks = [c.value for c in CheckType]

    dimension_str = str(data.get("dimension", ""))
    _fuzzy_validate(dimension_str, valid_dimensions, "dimension")
    dimension = DQDimension(dimension_str)

    severity_str = str(data.get("severity", Severity.WARNING.value))
    _fuzzy_validate(severity_str, valid_severities, "severity")
    severity = Severity(severity_str)

    check_str = str(data.get("check", ""))
    _fuzzy_validate(check_str, valid_checks, "check")

    dataset = str(data.get("dataset", ""))
    column: str | None = data.get("column")
    if column is not None:
        column = str(column)

    # Auto-generate ID when omitted
    rule_id = str(data.get("id", "")) if data.get("id") else (
        f"{dimension_str}-{dataset}-{column or 'table'}-{check_str}"
    )

    params = _parse_params(check_str, data.get("parameters"))

    status_str = str(data.get("status", RuleStatus.ACTIVE.value))
    status = RuleStatus(status_str)

    return Rule(
        id=rule_id,
        name=str(data.get("name", "")),
        dimension=dimension,
        rule_type=RuleType.ROW_LEVEL,
        severity=severity,
        dataset=dataset,
        column=column,
        check=check_str,
        params=params,
        condition=data.get("condition"),
        description=str(data.get("description", "")),
        tags=list(data.get("tags", [])),
        status=status,
        metadata=dict(data.get("metadata") or {}),
    )


def load_rules_from_file(path: Path) -> list[Rule]:
    """Load all rules defined in a single YAML file."""
    text = path.read_text(encoding="utf-8")
    doc: dict[str, Any] = yaml.safe_load(text) or {}
    raw_rules: list[dict[str, Any]] = doc.get("rules", [])
    return [_parse_rule(r) for r in raw_rules]


def load_rules_from_directory(directory: Path) -> list[Rule]:
    """Load rules from all ``.yaml`` / ``.yml`` files under *directory*."""
    rules: list[Rule] = []
    for ext in ("*.yaml", "*.yml"):
        for path in sorted(directory.glob(ext)):
            rules.extend(load_rules_from_file(path))
    return rules


def load_rules_from_path(path: Path) -> list[Rule]:
    """Load rules from either a YAML file or a directory of YAML files.

    This is the convenience entry point for CLI commands — callers don't have to
    know whether the user passed a single file or a directory.
    """
    if path.is_file():
        return load_rules_from_file(path)
    if path.is_dir():
        return load_rules_from_directory(path)
    raise FileNotFoundError(f"Rules path not found: {path}")
