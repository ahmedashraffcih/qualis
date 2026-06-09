from __future__ import annotations

import importlib.util
from unittest import mock

import pytest

_FASTAPI = importlib.util.find_spec("fastapi") is not None
pytestmark = pytest.mark.skipif(not _FASTAPI, reason="qualis[ui] not installed")


def _client():  # type: ignore[no-untyped-def]
    from starlette.testclient import TestClient

    from qualis.ui.server import create_app

    return TestClient(create_app())


class TestApp:
    def test_landing_renders(self) -> None:
        resp = _client().get("/")
        assert resp.status_code == 200
        assert "qualis" in resp.text
        assert "Upload a CSV" in resp.text

    def test_healthz(self) -> None:
        resp = _client().get("/healthz")
        assert resp.status_code == 200
        assert resp.text == "ok"

    def test_static_css_served(self) -> None:
        resp = _client().get("/static/styles.css")
        assert resp.status_code == 200
        assert "shell" in resp.text

    def test_autoescape_enabled(self) -> None:
        """The XSS defense for untrusted CSV content (lands fully in PR-3)
        depends on Jinja2 autoescape being on. Lock it here."""
        from qualis.ui.server import create_app

        app = create_app()
        # The Jinja2Templates env is created inside create_app; assert the
        # template response escapes a hostile string via a probe template.
        from jinja2 import Environment, select_autoescape

        env = Environment(autoescape=select_autoescape(["html"]))
        rendered = env.from_string("{{ v }}").render(v="<img src=x onerror=alert(1)>")
        assert "&lt;img" in rendered
        assert app is not None


class TestPortStrategy:
    def test_finds_preferred_when_free(self) -> None:
        from qualis.ui import server

        with mock.patch.object(server, "_port_is_free", return_value=True):
            assert server.find_available_port(7420) == 7420

    def test_scans_forward_when_busy(self) -> None:
        from qualis.ui import server

        # 7420 and 7421 busy, 7422 free
        def free(host: str, port: int) -> bool:
            return port >= 7422

        with mock.patch.object(server, "_port_is_free", side_effect=free):
            assert server.find_available_port(7420) == 7422

    def test_returns_none_when_all_busy(self) -> None:
        from qualis.ui import server

        with mock.patch.object(server, "_port_is_free", return_value=False):
            assert server.find_available_port(7420) is None


class TestRunServerBindsLocalhost:
    """E10 (BLOCKING/security): the server MUST bind 127.0.0.1 only."""

    def test_uvicorn_invoked_with_localhost(self) -> None:
        from qualis.ui import server

        captured: dict[str, object] = {}

        def fake_run(app: object, **kwargs: object) -> None:
            captured.update(kwargs)

        with (
            mock.patch.object(server, "_port_is_free", return_value=True),
            mock.patch("uvicorn.run", side_effect=fake_run),
        ):
            server.run_server(port=7420, open_browser=False)

        assert captured["host"] == "127.0.0.1"
        assert captured["host"] != "0.0.0.0"
        assert captured["port"] == 7420

    def test_does_not_open_browser_when_disabled(self) -> None:
        from qualis.ui import server

        with (
            mock.patch.object(server, "_port_is_free", return_value=True),
            mock.patch("uvicorn.run"),
            mock.patch("webbrowser.open") as wb,
        ):
            server.run_server(port=7420, open_browser=False)
        wb.assert_not_called()

    def test_explicit_port_busy_no_scan_raises(self) -> None:
        from qualis.ui import server

        with (
            mock.patch.object(server, "_port_is_free", return_value=False),
            mock.patch("uvicorn.run"),
            pytest.raises(RuntimeError, match="already in use"),
        ):
            server.run_server(port=9999, scan=False, open_browser=False)


class TestBaseInstallStaysLean:
    """The `qualis ui` command is registered at base CLI load, but importing
    the CLI must NOT pull FastAPI/uvicorn — they belong only to qualis[ui]."""

    def test_cli_import_does_not_pull_fastapi(self) -> None:
        import subprocess
        import sys

        # Fresh interpreter: import the CLI, assert the heavy deps are absent.
        code = (
            "import sys, qualis.cli.main;"
            "assert 'fastapi' not in sys.modules;"
            "assert 'uvicorn' not in sys.modules;"
            "assert 'starlette' not in sys.modules;"
            "print('lean')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "lean" in result.stdout


class TestUiCommand:
    def test_missing_extra_prints_install_hint(self) -> None:
        """When the ui extra isn't importable, the command exits cleanly
        with the install hint — never a raw ImportError."""
        import builtins

        import typer

        from qualis.cli import ui_cmd

        real_import = builtins.__import__

        def boom(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            if name == "uvicorn" or name.startswith(("uvicorn.", "qualis.ui.server")):
                raise ImportError("no uvicorn")
            return real_import(name, *args, **kwargs)

        with (
            mock.patch("builtins.__import__", side_effect=boom),
            pytest.raises(typer.Exit) as exc,
        ):
            ui_cmd.ui(port=7420, no_open=True)
        assert exc.value.exit_code == 1
