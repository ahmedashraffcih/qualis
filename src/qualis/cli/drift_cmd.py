"""qualis snapshot / qualis drift — capture baselines and detect data shifts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from qualis.adapters.duckdb.adapter import DuckDBAdapter
from qualis.config.loader import load_rules_from_path
from qualis.discover.drift_detector import snapshot_from_profile
from qualis.discover.profiler import profile_table
from qualis.discover.snapshot_store import SnapshotStore
from qualis.domain.drift import DriftSeverity, compare_snapshots

console = Console()


def _register_sample(adapter: DuckDBAdapter, sample: Path, table_name: str) -> None:
    if sample.suffix == ".csv":
        adapter.register_csv(table_name, str(sample))
    elif sample.suffix == ".parquet":
        adapter.register_parquet(table_name, str(sample))
    else:
        console.print(f"[red]Error:[/] Unsupported sample format '{sample.suffix}'.")
        raise typer.Exit(1)


def snapshot(
    rules: Path = typer.Option(  # noqa: B008
        ...,
        "--rules",
        "-r",
        help="Path to rules YAML file or directory.",
        show_default=False,
    ),
    sample: Path = typer.Option(  # noqa: B008
        ...,
        "--sample",
        "-s",
        help="CSV or Parquet sample representing the data the rules were accepted against.",
        show_default=False,
    ),
    snapshots_dir: Path = typer.Option(  # noqa: B008
        Path(".qualis/snapshots"),
        "--snapshots",
        help="Directory where ProfileSnapshots are stored.",
    ),
) -> None:
    """Capture a baseline ProfileSnapshot per rule.

    Run this after accepting rules — the snapshot freezes the profile the
    rule was approved against, so future `qualis drift` runs can detect
    underlying-data shifts.
    """
    if not (rules.is_dir() or rules.is_file()):
        console.print(f"[red]Error:[/] Rules path '[cyan]{rules}[/]' does not exist.")
        raise typer.Exit(1)
    if not sample.is_file():
        console.print(f"[red]Error:[/] Sample path '[cyan]{sample}[/]' is not a file.")
        raise typer.Exit(1)

    loaded_rules = load_rules_from_path(rules)
    store = SnapshotStore(snapshots_dir)

    adapter = DuckDBAdapter()
    rules_by_table = Counter(r.dataset for r in loaded_rules)
    profiles_by_table = {}
    for table_name in rules_by_table:
        _register_sample(adapter, sample, table_name)
        profiles_by_table[table_name] = profile_table(adapter, table_name)

    written = 0
    for rule in loaded_rules:
        profile = profiles_by_table[rule.dataset]
        snap = snapshot_from_profile(rule.id, rule.dataset, profile)
        store.save(snap)
        written += 1

    console.print(
        f"\n[bold green]Captured {written} snapshot(s)[/] → [cyan]{snapshots_dir}[/]"
    )


_SEVERITY_STYLE = {
    DriftSeverity.NOTICE: "yellow",
    DriftSeverity.WARNING: "orange3",
    DriftSeverity.CRITICAL: "red",
}


def drift(
    rules: Path = typer.Option(  # noqa: B008
        ...,
        "--rules",
        "-r",
        help="Path to rules YAML file or directory.",
        show_default=False,
    ),
    sample: Path = typer.Option(  # noqa: B008
        ...,
        "--sample",
        "-s",
        help="Current CSV or Parquet sample to compare against the baseline.",
        show_default=False,
    ),
    snapshots_dir: Path = typer.Option(  # noqa: B008
        Path(".qualis/snapshots"),
        "--snapshots",
        help="Directory where ProfileSnapshots are stored.",
    ),
    fail_on: DriftSeverity = typer.Option(  # noqa: B008
        DriftSeverity.CRITICAL,
        "--fail-on",
        help="Exit non-zero when any finding meets or exceeds this severity.",
        case_sensitive=False,
    ),
) -> None:
    """Detect drift between captured baselines and the current data.

    Compares the live profile of each rule's table against the baseline
    written by `qualis snapshot`. Reports per-metric findings classified
    as NOTICE / WARNING / CRITICAL.
    """
    if not (rules.is_dir() or rules.is_file()):
        console.print(f"[red]Error:[/] Rules path '[cyan]{rules}[/]' does not exist.")
        raise typer.Exit(1)
    if not sample.is_file():
        console.print(f"[red]Error:[/] Sample path '[cyan]{sample}[/]' is not a file.")
        raise typer.Exit(1)

    loaded_rules = load_rules_from_path(rules)
    store = SnapshotStore(snapshots_dir)

    adapter = DuckDBAdapter()
    table_names = {r.dataset for r in loaded_rules}
    current_profiles = {}
    for table_name in table_names:
        _register_sample(adapter, sample, table_name)
        current_profiles[table_name] = profile_table(adapter, table_name)

    all_findings = []
    missing_baselines = []
    for rule in loaded_rules:
        if not store.exists(rule.id):
            missing_baselines.append(rule.id)
            continue
        baseline = store.load(rule.id)
        current = snapshot_from_profile(rule.id, rule.dataset, current_profiles[rule.dataset])
        all_findings.extend(compare_snapshots(baseline, current))

    if missing_baselines:
        console.print(
            f"[dim]Skipped {len(missing_baselines)} rule(s) without snapshots: "
            f"{', '.join(missing_baselines[:5])}"
            f"{'…' if len(missing_baselines) > 5 else ''}[/]"
        )

    if not all_findings:
        console.print("\n[bold green]No drift detected.[/]\n")
        return

    table = Table(title="Drift findings", show_lines=False)
    table.add_column("Rule", style="cyan")
    table.add_column("Column")
    table.add_column("Metric")
    table.add_column("Baseline")
    table.add_column("Current")
    table.add_column("Δ", justify="right")
    table.add_column("Severity", justify="center")

    severity_order = {
        DriftSeverity.CRITICAL: 0,
        DriftSeverity.WARNING: 1,
        DriftSeverity.NOTICE: 2,
        DriftSeverity.INFO: 3,
    }
    all_findings.sort(key=lambda f: severity_order[f.severity])

    for f in all_findings:
        delta = f"{f.relative_change:+.1%}" if f.relative_change is not None else "—"
        style = _SEVERITY_STYLE.get(f.severity, "")
        table.add_row(
            f.rule_id,
            f.column,
            f.metric,
            f.baseline,
            f.current,
            delta,
            f"[{style}]{f.severity.value}[/]" if style else f.severity.value,
        )
    console.print(table)

    severity_threshold = severity_order[fail_on]
    if any(severity_order[f.severity] <= severity_threshold for f in all_findings):
        raise typer.Exit(1)
