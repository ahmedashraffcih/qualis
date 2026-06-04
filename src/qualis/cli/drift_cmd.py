"""qualis snapshot / qualis drift — capture baselines and detect data shifts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from qualis.adapters.duckdb.adapter import DuckDBAdapter
from qualis.config.loader import load_rules_from_path
from qualis.discover.drift_detector import snapshot_from_profile
from qualis.discover.profiler import profile_table
from qualis.discover.snapshot_store import CorruptSnapshotError, SnapshotStore
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


def _validate_inputs(rules: Path, sample: Path) -> None:
    if not (rules.is_dir() or rules.is_file()):
        console.print(f"[red]Error:[/] Rules path '[cyan]{rules}[/]' does not exist.")
        raise typer.Exit(1)
    if not sample.is_file():
        console.print(f"[red]Error:[/] Sample path '[cyan]{sample}[/]' is not a file.")
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
    """Capture one baseline ProfileSnapshot per referenced table.

    Run this after accepting rules — the snapshot freezes the profile
    each table was approved against, so future `qualis drift` runs can
    detect underlying-data shifts.
    """
    _validate_inputs(rules, sample)
    loaded_rules = load_rules_from_path(rules)
    store = SnapshotStore(snapshots_dir)

    adapter = DuckDBAdapter()
    tables = sorted({r.dataset for r in loaded_rules})
    for table_name in tables:
        _register_sample(adapter, sample, table_name)
        profile = profile_table(adapter, table_name)
        store.save(snapshot_from_profile(profile))

    console.print(
        f"\n[bold green]Captured {len(tables)} table snapshot(s)[/] → "
        f"[cyan]{snapshots_dir}[/]"
    )


_SEVERITY_STYLE = {
    DriftSeverity.NOTICE: "yellow",
    DriftSeverity.WARNING: "orange3",
    DriftSeverity.CRITICAL: "red",
}

_SEVERITY_ORDER = {
    DriftSeverity.CRITICAL: 0,
    DriftSeverity.WARNING: 1,
    DriftSeverity.NOTICE: 2,
    DriftSeverity.INFO: 3,
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

    Compares the live profile of each referenced table against its
    baseline (captured by `qualis snapshot`). Findings are emitted ONCE
    per (table, column, metric); each carries the rule ids it affects.
    """
    _validate_inputs(rules, sample)
    loaded_rules = load_rules_from_path(rules)
    store = SnapshotStore(snapshots_dir)

    # Group rules by table + column to attach affected rule ids
    rules_by_table_col: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for rule in loaded_rules:
        col = rule.column or "*"
        rules_by_table_col[rule.dataset][col].append(rule.id)

    adapter = DuckDBAdapter()
    all_findings = []
    missing_baselines: list[str] = []
    for table_name, cols in rules_by_table_col.items():
        if not store.exists(table_name):
            missing_baselines.append(table_name)
            continue
        try:
            baseline = store.load(table_name)
        except CorruptSnapshotError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise typer.Exit(1) from exc
        _register_sample(adapter, sample, table_name)
        current = snapshot_from_profile(profile_table(adapter, table_name))
        rules_by_column = {c: tuple(ids) for c, ids in cols.items()}
        all_findings.extend(
            compare_snapshots(baseline, current, rules_by_column=rules_by_column)
        )

    if missing_baselines:
        console.print(
            f"[dim]Skipped {len(missing_baselines)} table(s) without snapshots: "
            f"{', '.join(missing_baselines[:5])}"
            f"{'…' if len(missing_baselines) > 5 else ''}[/]"
        )

    if not all_findings:
        if missing_baselines and len(missing_baselines) == len(rules_by_table_col):
            # Every table is missing — almost certainly the user forgot to
            # run `qualis snapshot` first.
            console.print(
                "\n[yellow]No baselines found.[/] Run "
                "[cyan]qualis snapshot --rules ... --sample ...[/] first to capture "
                "baselines, then re-run drift.\n"
            )
            raise typer.Exit(1)
        console.print("\n[bold green]No drift detected.[/]\n")
        return

    table = Table(title="Drift findings", show_lines=False)
    table.add_column("Table", style="cyan")
    table.add_column("Column")
    table.add_column("Metric")
    table.add_column("Baseline")
    table.add_column("Current")
    table.add_column("Δ", justify="right")
    table.add_column("Severity", justify="center")
    table.add_column("Affected rules", style="dim")

    all_findings.sort(key=lambda f: _SEVERITY_ORDER[f.severity])

    for f in all_findings:
        delta = f"{f.relative_change:+.1%}" if f.relative_change is not None else "—"
        style = _SEVERITY_STYLE.get(f.severity, "")
        rules_str = ", ".join(f.affected_rules) if f.affected_rules else "—"
        table.add_row(
            f.table,
            f.column,
            f.metric,
            f.baseline,
            f.current,
            delta,
            f"[{style}]{f.severity.value}[/]" if style else f.severity.value,
            rules_str,
        )
    console.print(table)

    severity_threshold = _SEVERITY_ORDER[fail_on]
    if any(_SEVERITY_ORDER[f.severity] <= severity_threshold for f in all_findings):
        raise typer.Exit(1)
