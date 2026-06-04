"""JSON storage for ProfileSnapshots — one file per TABLE.

(Previously one file per rule, which produced N-times duplicate drift
findings when N rules referenced the same table. Per-table keys give
exactly one snapshot per table regardless of rule count.)

Layout::

    <root>/
        <table>.json

The store is a thin adapter: domain owns the shape, this module owns
the read/write path. No business logic.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path  # noqa: TC003

from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot


class CorruptSnapshotError(Exception):
    """Raised when a snapshot file is not valid JSON or has an unexpected shape."""


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _safe_filename(self, table: str) -> str:
        # Table identifiers can carry dots and slashes (e.g. ``schema.table``
        # or ``warehouse/schema/table``). Flatten to a single safe segment.
        return table.replace("/", "_").replace(".", "_") + ".json"

    def path_for(self, table: str) -> Path:
        return self._root / self._safe_filename(table)

    def exists(self, table: str) -> bool:
        return self.path_for(table).is_file()

    def save(self, snapshot: ProfileSnapshot) -> Path:
        payload = dataclasses.asdict(snapshot)
        # tuples → lists for JSON
        payload["columns"] = [dataclasses.asdict(c) for c in snapshot.columns]
        for col in payload["columns"]:
            col["sample_values"] = list(col["sample_values"])
        target = self.path_for(snapshot.table)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return target

    def load(self, table: str) -> ProfileSnapshot:
        path = self.path_for(table)
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CorruptSnapshotError(
                f"Snapshot file {path} is not valid JSON ({exc.msg}). "
                "Delete the file and re-run `qualis snapshot` to rebuild the baseline."
            ) from exc
        except OSError as exc:
            raise CorruptSnapshotError(
                f"Cannot read snapshot file {path}: {exc}"
            ) from exc
        try:
            columns = tuple(
                ColumnSnapshot(
                    column=c["column"],
                    inferred_type=c["inferred_type"],
                    total_count=c["total_count"],
                    null_count=c["null_count"],
                    null_fraction=c["null_fraction"],
                    distinct_count=c["distinct_count"],
                    distinct_fraction=c["distinct_fraction"],
                    min_value=c.get("min_value"),
                    max_value=c.get("max_value"),
                    sample_values=tuple(c.get("sample_values", [])),
                )
                for c in raw["columns"]
            )
            return ProfileSnapshot(
                table=raw["table"],
                captured_at=raw["captured_at"],
                row_count=raw["row_count"],
                columns=columns,
            )
        except (KeyError, TypeError) as exc:
            raise CorruptSnapshotError(
                f"Snapshot file {path} has an unexpected shape ({exc}). "
                "It may have been written by an incompatible Qualis version — "
                "delete it and re-run `qualis snapshot`."
            ) from exc

    def list_tables(self) -> list[str]:
        return sorted(p.stem for p in self._root.glob("*.json"))
