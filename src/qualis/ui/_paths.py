"""Filesystem locations for UI templates and static assets (stdlib-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

_UI_DIR = Path(__file__).parent
TEMPLATES_DIR: Final[Path] = _UI_DIR / "templates"
STATIC_DIR: Final[Path] = _UI_DIR / "static"
