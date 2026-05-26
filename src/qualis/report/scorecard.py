from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from qualis import __version__
from qualis.domain.enums import DQDimension

if TYPE_CHECKING:
    from qualis.domain.models import CheckResult, DatasetScore


_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_NAME = "template.html.j2"

_ALL_DIMENSIONS = list(DQDimension)


def _score_color(score_pct: int) -> str:
    if score_pct >= 90:
        return "#16a34a"
    if score_pct >= 70:
        return "#d97706"
    return "#dc2626"


def _score_class(score_pct: int) -> str:
    if score_pct >= 90:
        return "pass"
    if score_pct >= 70:
        return "warn"
    return "fail"


def _build_dimension_rows(
    score: DatasetScore,
    check_results: list[CheckResult] | None,
) -> list[dict[str, Any]]:
    """Build the template context list for all 9 DAMA dimensions."""
    # Index existing dimension scores by dimension
    measured: dict[DQDimension, Any] = {
        ds.dimension: ds for ds in score.dimension_scores
    }

    # Index check results by dimension for drilldown
    results_by_dim: dict[DQDimension, list[CheckResult]] = {}
    if check_results is not None:
        for cr in check_results:
            dim = cr.rule.dimension
            results_by_dim.setdefault(dim, []).append(cr)

    rows: list[dict[str, Any]] = []
    for dim in _ALL_DIMENSIONS:
        ds = measured.get(dim)
        if ds is None:
            rows.append(
                {
                    "name": dim.value.capitalize(),
                    "measured": False,
                    "score_pct": 0,
                    "bar_color": "#94a3b8",
                    "score_class": "none",
                    "passed": 0,
                    "total": 0,
                    "checks": [],
                }
            )
        else:
            pct = int(ds.score * 100)
            dim_checks: list[dict[str, Any]] = []
            for cr in results_by_dim.get(dim, []):
                dim_checks.append(
                    {
                        "rule_id": cr.rule.id,
                        "rule_name": cr.rule.name,
                        "passed": cr.passed,
                        "violation_count": cr.violation_count,
                    }
                )
            rows.append(
                {
                    "name": dim.value.capitalize(),
                    "measured": True,
                    "score_pct": pct,
                    "bar_color": _score_color(pct),
                    "score_class": _score_class(pct),
                    "passed": ds.passed,
                    "total": ds.total_checks,
                    "checks": dim_checks,
                }
            )

    return rows


def generate_html_report(
    score: DatasetScore,
    check_results: list[CheckResult] | None = None,
) -> str:
    """Generate a single-file HTML scorecard report.

    Parameters
    ----------
    score:
        The ``DatasetScore`` to render.
    check_results:
        Optional list of ``CheckResult`` objects used to populate the
        per-dimension drilldown table.  When ``None``, drilldown rows are
        omitted.

    Returns
    -------
    str
        A complete, self-contained HTML document.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(_TEMPLATE_NAME)

    score_pct = int(score.aggregate_score * 100)
    hero_color = _score_color(score_pct)
    passing_dimensions = sum(
        1 for ds in score.dimension_scores if int(ds.score * 100) >= 90
    )
    total_dimensions = len(_ALL_DIMENSIONS)

    context: dict[str, Any] = {
        "dataset": score.dataset,
        "score_pct": score_pct,
        "hero_color": hero_color,
        "passing_dimensions": passing_dimensions,
        "total_dimensions": total_dimensions,
        "critical_violations": score.critical_violations,
        "dimensions": _build_dimension_rows(score, check_results),
        "version": __version__,
        "generated_at": datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }

    return template.render(**context)


def save_html_report(
    score: DatasetScore,
    output_path: Path,
    check_results: list[CheckResult] | None = None,
) -> None:
    """Generate and save the HTML report to a file.

    Parameters
    ----------
    score:
        The ``DatasetScore`` to render.
    output_path:
        Destination file path.  Parent directories are created if they do
        not exist.
    check_results:
        Optional list of ``CheckResult`` objects for the drilldown table.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = generate_html_report(score, check_results)
    output_path.write_text(html, encoding="utf-8")
