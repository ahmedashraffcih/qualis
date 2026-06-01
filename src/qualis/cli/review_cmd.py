"""qualis review -- list/manage rules in the needs_evidence state."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003  (used at runtime)

import typer
from rich.console import Console

from qualis.config.loader import load_rules_from_path
from qualis.domain.enums import RuleStatus

console = Console()


def review(
    pending: bool = typer.Option(
        False,
        "--pending",
        help="List rules in needs_evidence status awaiting confirmation.",
    ),
    rules: Path = typer.Option(  # noqa: B008
        ...,
        "--rules",
        "-r",
        help="Path to rules YAML file or directory.",
        show_default=False,
    ),
) -> None:
    """Review rules awaiting confirmation.

    Today this surfaces ``needs_evidence`` rules so a reviewer can come
    back to them after gathering domain knowledge or talking to an SME.
    """
    try:
        all_rules = load_rules_from_path(rules)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1) from exc

    if pending:
        pending_rules = [r for r in all_rules if r.status == RuleStatus.NEEDS_EVIDENCE]
        if not pending_rules:
            console.print("\n[bold green]0 pending[/] — no rules awaiting confirmation.\n")
            return
        console.print(f"\n[bold yellow]{len(pending_rules)} pending[/] rule(s):\n")
        for r in pending_rules:
            reason = r.metadata.get("needs_evidence_reason", "(no reason recorded)")
            console.print(
                f"  [cyan]{r.id}[/]  {r.name}  "
                f"[dim]({r.dataset}.{r.column or '*'} · {r.check})[/]"
            )
            console.print(f"    Reason: [yellow]{reason}[/]")
        console.print()
    else:
        console.print(
            "[yellow]Hint:[/] use [cyan]--pending[/] to list rules awaiting confirmation."
        )
