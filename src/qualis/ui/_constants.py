"""Stdlib-only UI constants.

Lives apart from server.py so the CLI can read DEFAULT_PORT (for the
`qualis ui --port` option default) WITHOUT importing server.py, which
pulls FastAPI. Keeps the base install free of the `qualis[ui]` deps.
"""

from __future__ import annotations

from typing import Final

#: The interface the server is allowed to bind. Hard-coded, not configurable
#: (untrusted-CSV LAN-exposure guard — AgDR-0009, qualis#27 E10).
LOCALHOST: Final[str] = "127.0.0.1"

#: Preferred default port; the runner scans forward from here on conflict.
DEFAULT_PORT: Final[int] = 7420

#: How many ports to try (DEFAULT_PORT .. DEFAULT_PORT + PORT_SCAN_RANGE - 1).
PORT_SCAN_RANGE: Final[int] = 11
