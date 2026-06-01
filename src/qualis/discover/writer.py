"""Serialize RuleSuggestion lists to YAML — round-trips through the loader."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003  (used at runtime)
from typing import TYPE_CHECKING, Any

import yaml

from qualis.domain.enums import RuleStatus
from qualis.domain.params import (
    BetweenParams,
    CustomParams,
    InSetParams,
    NotNegativeParams,
    NotNullParams,
    RegexParams,
    RowCountParams,
    SqlParams,
    UniqueParams,
)

if TYPE_CHECKING:
    from qualis.discover.suggester import RuleSuggestion
    from qualis.domain.models import Rule


def _params_to_dict(params: Any) -> dict[str, Any]:
    if isinstance(params, (NotNullParams, UniqueParams, NotNegativeParams)):
        return {}
    if isinstance(params, BetweenParams):
        return {"min": params.min, "max": params.max}
    if isinstance(params, RegexParams):
        return {"pattern": params.pattern}
    if isinstance(params, SqlParams):
        return {"expression": params.expression}
    if isinstance(params, CustomParams):
        return {"handler": params.handler}
    if isinstance(params, InSetParams):
        return {"values": list(params.values)}
    if isinstance(params, RowCountParams):
        out: dict[str, Any] = {}
        if params.min is not None:
            out["min"] = params.min
        if params.max is not None:
            out["max"] = params.max
        return out
    return {}


def _rule_to_dict(rule: Rule) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": rule.id,
        "name": rule.name,
        "dimension": rule.dimension.value,
        "severity": rule.severity.value,
        "dataset": rule.dataset,
    }
    if rule.column is not None:
        out["column"] = rule.column
    out["check"] = rule.check
    params = _params_to_dict(rule.params)
    if params:
        out["parameters"] = params
    # Only emit status when it differs from the default (ACTIVE) — keeps
    # generated YAML clean for the common case.
    if rule.status != RuleStatus.ACTIVE:
        out["status"] = rule.status.value
    if rule.metadata:
        out["metadata"] = dict(rule.metadata)
    return out


def suggestions_to_yaml(suggestions: list[RuleSuggestion]) -> str:
    """Serialize accepted suggestions to YAML rule format."""
    rules_payload = [_rule_to_dict(s.rule) for s in suggestions]
    return yaml.safe_dump({"rules": rules_payload}, sort_keys=False)


def write_suggestions(suggestions: list[RuleSuggestion], path: Path) -> None:
    """Write suggestions as a YAML rules file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(suggestions_to_yaml(suggestions), encoding="utf-8")
