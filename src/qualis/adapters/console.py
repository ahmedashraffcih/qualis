from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from qualis.domain.models import DatasetScore
    from qualis.engine.diff import ScoreDiff


def print_score(score: DatasetScore, console: Console | None = None) -> None:
    """Print a rich-formatted terminal scorecard for *score*.

    Parameters
    ----------
    score:
        The ``DatasetScore`` to render.
    console:
        Optional ``rich.console.Console`` instance. A default ``Console``
        (stdout, auto-detect colour) is created when not provided.
    """
    c = console or Console()

    pct = int(score.aggregate_score * 100)
    if pct >= 90:
        color, status = "green", "PASSING"
    elif pct >= 70:
        color, status = "yellow", "WARNING"
    else:
        color, status = "red", "FAILING"

    header = (
        f"[bold magenta]QUALIS[/]  ·  Data Quality Report\n\n"
        f"        Score:  [bold {color}]{pct} / 100[/]\n"
        f"        Status: [{color}]● {status}[/]"
    )
    c.print(Panel(header, border_style="bright_black", padding=(1, 4)))

    table = Table(show_header=True, header_style="bold")
    table.add_column("Dimension", style="cyan", min_width=16)
    table.add_column("Score", justify="right", min_width=8)
    table.add_column("Checks", justify="right", min_width=10)
    table.add_column("", min_width=3)

    for ds in score.dimension_scores:
        pct_dim = int(ds.score * 100)
        if ds.score >= 0.9:
            indicator = "[green]✓[/]"
        elif ds.score >= 0.7:
            indicator = "[yellow]⚠[/]"
        else:
            indicator = "[red]✗[/]"
        table.add_row(
            ds.dimension.value.capitalize(),
            f"{pct_dim}%",
            f"{ds.passed}/{ds.total_checks}",
            indicator,
        )

    c.print(table)

    if score.total_violations > 0:
        c.print(
            f"\n[bold]{score.total_violations} violation(s)[/] "
            f"({score.critical_violations} critical)"
        )


def print_diff(diff: ScoreDiff, console: Console | None = None) -> None:
    """Print a rich-formatted terminal diff between two DatasetScore snapshots.

    Parameters
    ----------
    diff:
        The ``ScoreDiff`` to render.
    console:
        Optional ``rich.console.Console`` instance. A default ``Console``
        (stdout, auto-detect colour) is created when not provided.
    """
    c = console or Console()

    before_pct = int(diff.before_aggregate * 100)
    after_pct = int(diff.after_aggregate * 100)
    delta_pct = after_pct - before_pct

    if delta_pct > 0:
        delta_str = f"[green]↑ +{delta_pct}[/]"
    elif delta_pct < 0:
        delta_str = f"[red]↓ {delta_pct}[/]"
    else:
        delta_str = "[dim]—[/]"

    header = (
        "[bold magenta]QUALIS[/]  ·  Score Diff\n\n"
        f"        Before:  [bold]{before_pct} / 100[/]\n"
        f"        After:   [bold]{after_pct} / 100[/]\n"
        f"        Delta:   {delta_str}"
    )
    c.print(Panel(header, border_style="bright_black", padding=(1, 4)))

    table = Table(show_header=True, header_style="bold")
    table.add_column("Dimension", style="cyan", min_width=16)
    table.add_column("Before", justify="right", min_width=8)
    table.add_column("After", justify="right", min_width=8)
    table.add_column("Delta", justify="right", min_width=8)
    table.add_column("", min_width=3)

    for dd in diff.dimension_deltas:
        before_val = f"{int(dd.before_score * 100)}%" if dd.before_score is not None else "—"
        after_val = f"{int(dd.after_score * 100)}%" if dd.after_score is not None else "—"

        dim_delta = int(dd.delta * 100)
        if dim_delta > 0:
            delta_cell = f"[green]↑ +{dim_delta}[/]"
            indicator = "[green]✓[/]"
        elif dim_delta < 0:
            delta_cell = f"[red]↓ {dim_delta}[/]"
            indicator = "[red]✗[/]"
        else:
            delta_cell = "[dim]—[/]"
            indicator = "[green]✓[/]"

        table.add_row(
            dd.dimension.value.capitalize(),
            before_val,
            after_val,
            delta_cell,
            indicator,
        )

    c.print(table)

    viol_delta = diff.after_violations - diff.before_violations
    if viol_delta != 0:
        sign = "+" if viol_delta > 0 else ""
        color = "red" if viol_delta > 0 else "green"
        c.print(
            f"\nViolations: [bold]{diff.before_violations}[/] → "
            f"[bold]{diff.after_violations}[/]  "
            f"([{color}]{sign}{viol_delta}[/])"
        )
