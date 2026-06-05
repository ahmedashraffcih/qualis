from __future__ import annotations

import difflib
import os
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import yaml

from qualis.domain.condition import ConditionError, parse_condition
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
        if "min" not in params or "max" not in params:
            raise ValueError(
                "check 'between' requires both 'min' and 'max' under parameters: "
                f"got {sorted(params.keys()) or 'no parameters'}"
            )
        return BetweenParams(
            min=_resolve_template_vars(str(params["min"])),
            max=_resolve_template_vars(str(params["max"])),
        )
    if check == CheckType.REGEX:
        if "pattern" not in params or not str(params["pattern"]).strip():
            raise ValueError(
                "check 'regex' requires non-empty 'pattern' under parameters"
            )
        return RegexParams(pattern=str(params["pattern"]))
    if check == CheckType.SQL:
        if "expression" not in params or not str(params["expression"]).strip():
            raise ValueError(
                "check 'sql' requires non-empty 'expression' under parameters"
            )
        return SqlParams(expression=str(params["expression"]))
    if check == CheckType.CUSTOM:
        if "handler" not in params or not str(params["handler"]).strip():
            raise ValueError(
                "check 'custom' requires non-empty 'handler' under parameters "
                "(module.path.callable)"
            )
        return CustomParams(handler=str(params["handler"]))
    if check == CheckType.IN_SET:
        if "values" not in params:
            raise ValueError(
                "check 'in_set' requires 'values' (a non-empty list) under parameters"
            )
        raw_values = params["values"]
        if not isinstance(raw_values, list) or not raw_values:
            raise ValueError(
                "check 'in_set' requires 'values' to be a non-empty list"
            )
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
        if "reference" not in params or "key_column" not in params:
            raise ValueError(
                "check 'reference_lookup' requires both 'reference' and 'key_column' "
                f"under parameters: got {sorted(params.keys()) or 'no parameters'}"
            )
        reference_schema = params.get("reference_schema")
        return ReferenceLookupParams(
            reference=str(params["reference"]),
            key_column=str(params["key_column"]),
            reference_schema=(
                str(reference_schema) if reference_schema is not None else None
            ),
        )
    # Unreachable — check has already been validated against CheckType values
    raise ValueError(f"Unhandled check type: {check}")  # pragma: no cover


def _validated_condition(data: dict[str, Any]) -> str | None:
    """Validate `condition` at the trust boundary (AgDR-0005, load time).

    The error is located — rule id + the offending text — so a bad
    condition is a one-glance fix instead of a runtime adapter traceback.
    """
    condition = data.get("condition")
    if condition is None:
        return None
    try:
        parse_condition(str(condition))
    except ConditionError as exc:
        rule_id = data.get("id", "<no id>")
        raise ValueError(
            f"rule {rule_id!r}: invalid condition {condition!r}: {exc}"
        ) from exc
    return str(condition)


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
        condition=_validated_condition(data),
        description=str(data.get("description", "")),
        tags=list(data.get("tags", [])),
        status=status,
        metadata=dict(data.get("metadata") or {}),
    )


def _check_for_duplicate_ids(rules: list[Rule], source: str) -> None:
    """Reject loads where two rules share an ``id``.

    Silent shadowing was the original behaviour and produced hard-to-debug
    rule loss (the second rule with the same id wins or the first wins
    depending on dict-iteration order). Loud failure is the right shape.
    """
    seen: dict[str, int] = {}
    for r in rules:
        seen[r.id] = seen.get(r.id, 0) + 1
    dups = sorted(rid for rid, n in seen.items() if n > 1)
    if dups:
        raise ValueError(
            f"Duplicate rule id(s) in {source}: {dups}. "
            "Every rule must have a unique id."
        )


def load_rules_from_file(path: Path) -> list[Rule]:
    """Load all rules defined in a single YAML file."""
    text = path.read_text(encoding="utf-8")
    doc: dict[str, Any] = yaml.safe_load(text) or {}
    raw_rules: list[dict[str, Any]] = doc.get("rules", [])
    rules = [_parse_rule(r) for r in raw_rules]
    _check_for_duplicate_ids(rules, source=str(path))
    return rules


def load_rules_from_directory(directory: Path) -> list[Rule]:
    """Load rules from all ``.yaml`` / ``.yml`` files under *directory*."""
    rules: list[Rule] = []
    for ext in ("*.yaml", "*.yml"):
        for path in sorted(directory.glob(ext)):
            rules.extend(load_rules_from_file(path))
    _check_for_duplicate_ids(rules, source=str(directory))
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
