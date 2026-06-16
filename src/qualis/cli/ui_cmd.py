"""`qualis ui` — launch the local browser UI (qualis#27).

Lives in its own module and lazy-imports the ``qualis[ui]`` dependencies
inside the command body so the base install never pays for FastAPI/uvicorn
and a missing extra fails with a clean hint, not an ImportError at load.
"""

from __future__ import annotations

import typer

from qualis.ui._constants import DEFAULT_PORT

_INSTALL_HINT = (
    "The qualis UI needs the optional 'ui' dependencies.\n"
    "Install them with:\n\n"
    "    pip install 'qualis[ui]'\n\n"
    "then re-run `qualis ui`."
)


def ui(
    port: int = typer.Option(
        DEFAULT_PORT,
        "--port",
        help=(
            "Port to bind on localhost. If busy and --port was NOT given, "
            f"qualis scans forward from {DEFAULT_PORT}. Passing --port "
            "explicitly disables the scan (the port is honoured or fails)."
        ),
    ),
    no_open: bool = typer.Option(
        False,
        "--no-open",
        help="Don't auto-open the browser (useful for headless/remote runs).",
    ),
) -> None:
    """Launch the qualis browser UI on localhost.

    Upload a CSV, review the suggested rules with their evidence, run the
    checks, and export a rulebook — the full journey, no YAML by hand.
    The server binds 127.0.0.1 only; your data never leaves your machine.
    """
    try:
        import uvicorn  # noqa: F401

        from qualis.ui.server import run_server
    except ImportError:
        typer.echo(_INSTALL_HINT, err=True)
        raise typer.Exit(1) from None

    # Explicit --port disables the auto-scan; the default port keeps it.
    scan = port == DEFAULT_PORT
    try:
        run_server(port=port, scan=scan, open_browser=not no_open)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
