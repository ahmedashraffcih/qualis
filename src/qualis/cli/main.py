from __future__ import annotations

import dataclasses
import json
import sys
import webbrowser
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from qualis import __version__
from qualis.adapters.console import print_diff, print_score
from qualis.bootstrap import create_checker
from qualis.config.loader import load_rules_from_directory
from qualis.config.settings import QualisSettings
from qualis.domain.params import CustomParams
from qualis.report.scorecard import save_html_report

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


class ReportFormat(StrEnum):
    html = "html"
    json = "json"


@app.command()
def report(
    rules: Path = typer.Option(  # noqa: B008
        ...,
        "--rules",
        "-r",
        help="Path to the rules directory containing YAML files.",
        show_default=False,
    ),
    sample: Path = typer.Option(  # noqa: B008
        ...,
        "--sample",
        "-s",
        help="Path to a CSV or Parquet sample file to validate.",
        show_default=False,
    ),
    format: ReportFormat = typer.Option(  # noqa: A002,B008
        ReportFormat.html,
        "--format",
        "-f",
        help="Output format: html or json.",
        case_sensitive=False,
    ),
    output: Path = typer.Option(  # noqa: B008
        Path("qualis-report.html"),
        "--output",
        "-o",
        help="Output file path.",
    ),
    allow_custom: bool = typer.Option(
        False,
        "--allow-custom/--no-allow-custom",
        help="Allow rules that use the 'custom' check type.",
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
) -> None:
    """Generate a quality report (HTML scorecard or JSON).

    Runs all data quality checks and emits either a self-contained HTML
    scorecard (default) or a JSON export.  The HTML report is opened in
    the default browser automatically.  Exits with code 1 when the score
    falls below --fail-on-score.
    """
    if not rules.is_dir():
        console.print(f"[red]Error:[/] Rules path '[cyan]{rules}[/]' is not a directory.")
        raise typer.Exit(1)

    if not sample.is_file():
        console.print(f"[red]Error:[/] Sample path '[cyan]{sample}[/]' is not a file.")
        raise typer.Exit(1)

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
        score, check_results = runner.run_detailed()
    except Exception as exc:  # pragma: no cover
        console.print(f"[red]Check failed:[/] {exc}")
        raise typer.Exit(1) from exc

    if format == ReportFormat.html:
        # Derive a sensible default output name if the user left it as the
        # default but switched format to json — keep .html for html output.
        save_html_report(score, output, check_results=check_results)
        console.print(
            f"\n[bold green]HTML report saved[/] → [cyan]{output}[/]"
        )
        webbrowser.open(output.resolve().as_uri())
    else:
        payload = _asdict_safe(score)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        console.print(
            f"\n[bold green]JSON report saved[/] → [cyan]{output}[/]"
        )

    score_pct = int(score.aggregate_score * 100)
    if fail_on_score > 0 and score_pct < fail_on_score:
        console.print(
            f"\n[red]Score {score_pct} is below threshold {fail_on_score} — failing.[/]"
        )
        raise typer.Exit(1)


@app.command()
def diff(
    before: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the 'before' JSON report.",
        show_default=False,
    ),
    after: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the 'after' JSON report.",
        show_default=False,
    ),
    output_format: OutputFormat = typer.Option(  # noqa: B008
        OutputFormat.table,
        "--output-format",
        "-f",
        help="Output format: table or json.",
        case_sensitive=False,
    ),
    fail_on_regression: bool = typer.Option(
        False,
        "--fail-on-regression",
        help="Exit with code 1 if any dimension's score regressed.",
    ),
) -> None:
    """Compare quality scores between two report snapshots.

    Loads two JSON reports (produced by ``qualis report --format json``) and
    renders a per-dimension delta. Use --fail-on-regression in CI to gate on
    any dimension score that dropped between runs.
    """
    from qualis.engine.diff import compute_diff
    from qualis.report.loader import load_report

    if not before.is_file():
        console.print(f"[red]Error:[/] Before report '[cyan]{before}[/]' is not a file.")
        raise typer.Exit(1)
    if not after.is_file():
        console.print(f"[red]Error:[/] After report '[cyan]{after}[/]' is not a file.")
        raise typer.Exit(1)

    before_score = load_report(before)
    after_score = load_report(after)
    result = compute_diff(before_score, after_score)

    if output_format == OutputFormat.json:
        payload = _asdict_safe(result)
        console.print_json(json.dumps(payload, default=str))
    else:
        print_diff(result, console)

    if fail_on_regression:
        regressed = [d for d in result.dimension_deltas if d.delta < 0]
        if regressed:
            names = ", ".join(d.dimension.value for d in regressed)
            console.print(f"\n[red]Regression detected in: {names} — failing.[/]")
            raise typer.Exit(1)


@app.command()
def discover(
    sample: Path = typer.Option(  # noqa: B008
        ...,
        "--sample",
        "-s",
        help="Path to a CSV or Parquet sample file to profile.",
        show_default=False,
    ),
    table: str = typer.Option(
        "",
        "--table",
        "-t",
        help="Table name to register (defaults to the sample file stem).",
    ),
    output: Path = typer.Option(  # noqa: B008
        Path("rules/discovered.yaml"),
        "--output",
        "-o",
        help="Output YAML file to write accepted suggestions.",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Accept all suggestions without prompting (for CI).",
    ),
) -> None:
    """Profile data and suggest DQ rules — review interactively or in batch.

    Statistical, deterministic profiling. No LLM required. The suggestions
    are pure heuristics over observed statistics — review them carefully
    before promoting to production rules.
    """
    from qualis.adapters.duckdb.adapter import DuckDBAdapter
    from qualis.discover.profiler import profile_table
    from qualis.discover.suggester import suggest_rules
    from qualis.discover.writer import write_suggestions

    if not sample.is_file():
        console.print(f"[red]Error:[/] Sample path '[cyan]{sample}[/]' is not a file.")
        raise typer.Exit(1)

    table_name = table or sample.stem
    adapter = DuckDBAdapter()
    if sample.suffix == ".csv":
        adapter.register_csv(table_name, str(sample))
    elif sample.suffix == ".parquet":
        adapter.register_parquet(table_name, str(sample))
    else:
        console.print(f"[red]Error:[/] Unsupported sample format '{sample.suffix}'.")
        raise typer.Exit(1)

    console.print(f"\nProfiling [cyan]{table_name}[/]…")
    profile = profile_table(adapter, table_name)
    console.print(
        f"  [dim]→ {profile.row_count} rows, {len(profile.columns)} columns[/]\n"
    )

    suggestions = suggest_rules(profile)
    if not suggestions:
        console.print("[yellow]No suggestions generated — try a richer sample.[/]")
        raise typer.Exit(0)

    accepted = []
    if batch:
        accepted = list(suggestions)
        for s in accepted:
            console.print(f"  [green]✓[/] {s.rule.id}  [dim]({s.confidence})[/]")
    else:
        for i, s in enumerate(suggestions, 1):
            console.print(
                f"\n[bold]({i}/{len(suggestions)})[/] "
                f"Suggested: [cyan]{s.rule.dataset}.{s.rule.column}[/] · "
                f"[magenta]{s.rule.check}[/]"
            )
            if isinstance(s.rule.params, type(s.rule.params)) and s.rule.params.__dict__:
                console.print(f"  Parameters: [dim]{s.rule.params}[/]")
            console.print(
                f"  Dimension: [cyan]{s.rule.dimension.value}[/] · "
                f"Confidence: [magenta]{s.confidence}[/] · "
                f"[dim]{s.rationale}[/]"
            )
            choice = typer.prompt("Accept (y), Skip (n), Quit (q)?", default="n").strip().lower()
            if choice == "q":
                break
            if choice == "y":
                accepted.append(s)

    if not accepted:
        console.print("\n[yellow]No suggestions accepted.[/]")
        raise typer.Exit(0)

    write_suggestions(accepted, output)
    console.print(
        f"\n[bold green]✓ {len(accepted)} rule(s) written to[/] [cyan]{output}[/]"
    )
    console.print(f"  Run [bold]qualis validate --rules {output.parent}[/] to verify.")
