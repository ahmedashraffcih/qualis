from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qualis.domain.enums import DQDimension, Severity
from qualis.domain.rule_engine import RuleEngine
from qualis.domain.scoring import compute_dataset_score, compute_dimension_scores

if TYPE_CHECKING:
    from qualis.domain.models import DatasetScore, Rule


class CheckRunner:
    """Orchestrates rule evaluation, optional redaction, and scoring.

    Parameters
    ----------
    adapter:
        Any object that satisfies ``DatabasePort`` — passed through to
        ``RuleEngine`` without importing from the ports layer.
    rules:
        The list of ``Rule`` objects to evaluate.
    weights:
        Per-dimension weight overrides for the aggregate score calculation.
    schema:
        Optional default schema forwarded to ``RuleEngine``.
    redact:
        When ``True``, replace ``actual_value`` on every ``Violation`` with
        ``"[REDACTED]"`` before the caller sees the results.
    """

    def __init__(
        self,
        adapter: Any,
        rules: list[Rule],
        weights: dict[DQDimension, float],
        schema: str = "",
        redact: bool = False,
    ) -> None:
        self._engine = RuleEngine(adapter, schema)
        self._rules = rules
        self._weights = weights
        self._redact = redact

    def run(self) -> DatasetScore:
        """Evaluate all rules and return an aggregated ``DatasetScore``."""
        results = self._engine.evaluate_all(self._rules)

        if self._redact:
            for r in results:
                for v in r.violations:
                    object.__setattr__(v, "actual_value", "[REDACTED]")

        datasets = {r.rule.dataset for r in results}
        dataset = next(iter(datasets)) if datasets else "unknown"

        total_violations = sum(r.violation_count for r in results)
        critical_violations = sum(
            r.violation_count
            for r in results
            if r.rule.severity == Severity.CRITICAL
        )

        dim_scores = compute_dimension_scores(results, dataset)
        return compute_dataset_score(
            dim_scores,
            self._weights,
            dataset,
            total_violations=total_violations,
            critical_violations=critical_violations,
        )
