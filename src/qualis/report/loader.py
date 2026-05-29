from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003  (used at runtime: path.exists / path.read_text)

from qualis.domain.enums import DQDimension
from qualis.domain.models import DatasetScore, DimensionScore


def load_report(path: Path) -> DatasetScore:
    """Load a DatasetScore from a JSON report file produced by ``qualis report --format json``.

    Parameters
    ----------
    path:
        Path to the JSON file.

    Returns
    -------
    DatasetScore
        Reconstructed score with fully typed ``DimensionScore`` objects.

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    ValueError
        When the JSON structure is missing expected keys.
    """
    if not path.exists():
        raise FileNotFoundError(f"Report file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    dimension_scores: list[DimensionScore] = []
    for ds_raw in raw.get("dimension_scores", []):
        dimension_scores.append(
            DimensionScore(
                dimension=DQDimension(ds_raw["dimension"]),
                dataset=ds_raw["dataset"],
                total_checks=ds_raw["total_checks"],
                passed=ds_raw["passed"],
                failed=ds_raw["failed"],
                score=ds_raw["score"],
                weight=ds_raw.get("weight", 1.0),
            )
        )

    return DatasetScore(
        dataset=raw["dataset"],
        dimension_scores=dimension_scores,
        aggregate_score=raw["aggregate_score"],
        total_violations=raw["total_violations"],
        critical_violations=raw["critical_violations"],
    )
