"""FastAPI app factory + localhost server runner for the qualis UI.

Security posture (AgDR-0009, qualis#27):
- The server binds ``127.0.0.1`` ONLY — never widened by a flag in v1.
  CSV content is untrusted; LAN exposure would leak a tester's local data.
- Templates use Jinja2 autoescape so any CSV-derived value rendered into
  the DOM is HTML-escaped (the full XSS pass lands in PR-3; the default is
  established here).

This module imports FastAPI at top level. That is intentional and safe:
``server.py`` is only ever imported when the UI actually runs (the CLI
reads :mod:`qualis.ui._constants` for the port default and lazy-imports
this module inside the ``qualis ui`` handler). The base install never
loads FastAPI. Importing FastAPI here — not inside ``create_app`` — is
also what lets FastAPI resolve the ``Request`` annotation on the routes
for dependency injection.
"""

from __future__ import annotations

import socket
import webbrowser

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from qualis.ui._constants import DEFAULT_PORT, LOCALHOST, PORT_SCAN_RANGE
from qualis.ui._paths import STATIC_DIR, TEMPLATES_DIR

__all__ = [
    "DEFAULT_PORT",
    "LOCALHOST",
    "PORT_SCAN_RANGE",
    "create_app",
    "find_available_port",
    "run_server",
]


def create_app() -> FastAPI:
    app = FastAPI(title="qualis", docs_url=None, redoc_url=None)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    # Lock autoescape on: a future template-config change must not silently
    # disable the XSS escaping that untrusted CSV content relies on (PR-3).
    templates.env.autoescape = True

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "landing.html", {})

    @app.get("/healthz", response_class=HTMLResponse)
    def healthz() -> HTMLResponse:
        return HTMLResponse("ok")

    return app


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.connect_ex((host, port)) != 0


def find_available_port(
    preferred: int = DEFAULT_PORT,
    *,
    host: str = LOCALHOST,
    scan: int = PORT_SCAN_RANGE,
) -> int | None:
    """First free port at or after ``preferred`` (OQ-7); None if all taken."""
    for port in range(preferred, preferred + scan):
        if _port_is_free(host, port):
            return port
    return None


def run_server(
    *,
    port: int = DEFAULT_PORT,
    scan: bool = True,
    open_browser: bool = True,
) -> None:
    """Start the UI on localhost.

    Binds ``127.0.0.1`` unconditionally. With ``scan`` (default), a busy
    ``port`` falls forward to the next free one and the chosen URL is
    printed; without it, a busy port is a hard error (explicit ``--port``).
    Opening the browser is the product behaviour of ``qualis ui`` — tests
    pass ``open_browser=False``.
    """
    if scan:
        chosen = find_available_port(port, scan=PORT_SCAN_RANGE)
    else:
        chosen = port if _port_is_free(LOCALHOST, port) else None

    if chosen is None:
        if scan:
            raise RuntimeError(
                f"no free port in {port}..{port + PORT_SCAN_RANGE - 1}; "
                f"pass --port to choose one explicitly"
            )
        raise RuntimeError(f"port {port} is already in use")

    url = f"http://{LOCALHOST}:{chosen}"
    print(f"qualis UI running at {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)

    uvicorn.run(create_app(), host=LOCALHOST, port=chosen, log_level="warning")
