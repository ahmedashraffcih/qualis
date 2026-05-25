from __future__ import annotations

import dataclasses
import json
import sys
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from qualis import __version__
from qualis.adapters.console import print_score
from qualis.bootstrap import create_checker
from qualis.config.loader import load_rules_from_directory
from qualis.config.settings import QualisSettings
from qualis.domain.params import CustomParams

app = typer.Typer(
    name="qualis",
    help=(
        "[bold magenta]Qualis[/] — Data quality framework that tells you "
        "[italic]what[/] failed, not just that something did."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)

console = Console()

_INIT_COMPLETENESS_YAML = """\
rules:
  - id: DQ-COMP-001
    name: "Column value is required"
    dimension: completeness
    severity: critical
    dataset: my_table
    column: my_column
    check: not_null
"""

_INIT_GITIGNORE = """\
.env
__pycache__/
*.pyc
.qualis/
"""


@app.command()
def version() -> None:
    """Print the installed Qualis version."""
    console.print(f"qualis {__version__}")


@app.command()
def init(
    directory: Path = typer.Argument(  # noqa: B008
        Path("."),
        help="Target directory for the scaffolded project (default: current directory).",
        show_default=True,
    ),
) -> None:
    """Scaffold a new Qualis project with a starter rules directory.

    Creates:

    \b
      rules/completeness.yaml   — example not_null rule
      .gitignore                — ignores .env and __pycache__/
    """
    rules_dir = directory / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    completeness_file = rules_dir / "completeness.yaml"
    if not completeness_file.exists():
        completeness_file.write_text(_INIT_COMPLETENESS_YAML, encoding="utf-8")

    gitignore = directory / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(_INIT_GITIGNORE, encoding="utf-8")

    console.print(f"\n[bold green]Qualis project initialised[/] in [cyan]{directory}[/]\n")
    console.print("Next steps:\n")
    console.print(
        "  1. Edit [cyan]rules/completeness.yaml[/] to describe your data quality rules."
    )
    console.print(
        "  2. Run [cyan]qualis validate --rules rules/[/] to confirm your YAML is valid."
    )
    console.print(
        "  3. Run [cyan]qualis check --rules rules/ --sample data.csv[/] against a sample file.\n"
    )


@app.command()
def validate(
    rules: Path = typer.Option(  # noqa: B008
        ...,
        "--rules",
        help="Path to the rules directory containing YAML files.",
        show_default=False,
    ),
) -> None:
    """Validate the syntax of all YAML rule files in a directory.

    Parses every rule and reports any errors.  Exits with code 1 when
    validation fails.
    """
    if not rules.is_dir():
        console.print(f"[red]Error:[/] Rules path '[cyan]{rules}[/]' is not a directory.")
        raise typer.Exit(1)

    try:
        loaded = load_rules_from_directory(rules)
    except ValueError as exc:
        console.print(f"[red]Validation failed:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        f"\n[bold green]{len(loaded)} rule(s) valid[/] in [cyan]{rules}[/]\n"
    )
    for rule in loaded:
        console.print(
            f"  [cyan]{rule.id}[/]  {rule.name}  "
            f"([dim]{rule.dimension.value} · {rule.severity.value}[/])"
        )
    console.print()


class OutputFormat(StrEnum):
    table = "table"
    json = "json"


def _asdict_safe(obj: Any) -> Any:
    """Recursively convert dataclass / Enum / nested structures to JSON-safe types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _asdict_safe(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_asdict_safe(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _asdict_safe(v) for k, v in obj.items()}
    return obj


@app.command()
def check(
    rules: Path = typer.Option(  # noqa: B008
        ...,
        "--rules",
        help="Path to the rules directory containing YAML files.",
        show_default=False,
    ),
    sample: Path = typer.Option(  # noqa: B008
        ...,
        "--sample",
        help="Path to a CSV or Parquet sample file to validate.",
        show_default=False,
    ),
    fail_on_score: int = typer.Option(
        0,
        "--fail-on-score",
        help=(
            "Exit with code 1 when the aggregate score (0-100) is below this threshold. "
            "Default 0 means never fail on score alone."
        ),
        min=0,
        max=100,
    ),
    allow_custom: bool = typer.Option(
        False,
        "--allow-custom/--no-allow-custom",
        help="Allow rules that use the 'custom' check type.",
    ),
    output_format: OutputFormat = typer.Option(  # noqa: B008
        OutputFormat.table,
        "--output-format",
        help="Output format: 'table' (rich terminal) or 'json'.",
        case_sensitive=False,
    ),
) -> None:
    """Run data quality checks against a sample CSV or Parquet file.

    Loads rules from the given directory, evaluates them against the
    sample, and prints a score report.  Exits with code 1 when the
    score falls below --fail-on-score or when a blocking error is found.
    """
    if not rules.is_dir():
        console.print(f"[red]Error:[/] Rules path '[cyan]{rules}[/]' is not a directory.")
        raise typer.Exit(1)

    if not sample.is_file():
        console.print(f"[red]Error:[/] Sample path '[cyan]{sample}[/]' is not a file.")
        raise typer.Exit(1)

    # Validate rules first so we can detect CustomParams before running
    try:
        loaded_rules = load_rules_from_directory(rules)
    except ValueError as exc:
        console.print(f"[red]Rules validation failed:[/] {exc}")
        raise typer.Exit(1) from exc

    if not allow_custom:
        custom_rule_ids = [r.id for r in loaded_rules if isinstance(r.params, CustomParams)]
        if custom_rule_ids:
            console.print(
                "[red]Error:[/] Rules with 'custom' check type are not allowed unless "
                "--allow-custom is set.\n"
                f"  Affected rules: {', '.join(custom_rule_ids)}"
            )
            raise typer.Exit(1)

    settings = QualisSettings(rules_dir=rules, allow_custom=allow_custom)
    runner = create_checker(settings, sample_path=sample)

    try:
        score = runner.run()
    except Exception as exc:  # pragma: no cover
        console.print(f"[red]Check failed:[/] {exc}")
        raise typer.Exit(1) from exc

    if output_format == OutputFormat.json:
        payload = _asdict_safe(score)
        sys.stdout.write(json.dumps(payload, indent=2, default=str) + "\n")
    else:
        print_score(score)

    score_pct = int(score.aggregate_score * 100)
    if fail_on_score > 0 and score_pct < fail_on_score:
        console.print(
            f"\n[red]Score {score_pct} is below threshold {fail_on_score} — failing.[/]"
        )
        raise typer.Exit(1)
