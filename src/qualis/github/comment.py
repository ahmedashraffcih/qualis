"""Format a Qualis JSON report as a Markdown PR comment.

The output stays under 20 rendered lines so it doesn't dominate the PR thread.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003  (used at runtime)
from typing import Any


def _status_for_score(pct: int) -> tuple[str, str]:
    """Return (emoji, label) for an aggregate score percentage."""
    if pct >= 90:
        return "✅", "PASSING"
    if pct >= 70:
        return "⚠️", "WARNING"
    return "❌", "FAILING"


def _dim_emoji(score: float) -> str:
    if score >= 0.9:
        return "✅ Pass"
    if score >= 0.7:
        return "⚠️ Warn"
    return "❌ Fail"


def format_pr_comment(report: dict[str, Any], commit_sha: str | None = None) -> str:
    """Format a Qualis report dict as a Markdown PR comment.

    Parameters
    ----------
    report:
        A dict matching the structure emitted by ``qualis report --format json``.
    commit_sha:
        Optional commit SHA to include in the footer for traceability.
    """
    aggregate = float(report.get("aggregate_score", 0.0))
    pct = int(aggregate * 100)
    emoji, label = _status_for_score(pct)

    lines: list[str] = [
        "## Qualis Data Quality Report",
        "",
        f"{emoji} **Score: {pct} / 100** — `{label}`",
        "",
        "| Dimension      | Result | Score |",
        "|----------------|--------|-------|",
    ]

    for ds in report.get("dimension_scores", []):
        dim_name = str(ds.get("dimension", "")).capitalize()
        score = float(ds.get("score", 0.0))
        dim_pct = int(score * 100)
        lines.append(f"| {dim_name:<14} | {_dim_emoji(score)} | {dim_pct}% |")

    total = int(report.get("total_violations", 0))
    critical = int(report.get("critical_violations", 0))
    if total > 0:
        lines.extend(["", f"**{total} violations** ({critical} critical)"])

    footer = "> Run by `qualis-github-action`"
    if commit_sha:
        short = commit_sha[:7]
        footer += f" on commit `{short}`"
    lines.extend(["", footer])

    return "\n".join(lines)


def render_comment_from_file(report_path: Path, commit_sha: str | None = None) -> str:
    """Load a JSON report file and return the formatted PR comment."""
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    return format_pr_comment(raw, commit_sha=commit_sha)
