from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from qualis.domain.models import DatasetScore


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
