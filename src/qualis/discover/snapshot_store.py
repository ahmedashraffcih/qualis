"""JSON storage for ProfileSnapshots — one file per rule.

Layout::

    <root>/
        <rule_id>.json

The store is a thin adapter: domain owns the shape, this module owns
the read/write path. No business logic.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path  # noqa: TC003

from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def path_for(self, rule_id: str) -> Path:
        return self._root / f"{rule_id}.json"

    def exists(self, rule_id: str) -> bool:
        return self.path_for(rule_id).is_file()

    def save(self, snapshot: ProfileSnapshot) -> Path:
        payload = dataclasses.asdict(snapshot)
        # tuples → lists for JSON
        payload["columns"] = [dataclasses.asdict(c) for c in snapshot.columns]
        for col in payload["columns"]:
            col["sample_values"] = list(col["sample_values"])
        target = self.path_for(snapshot.rule_id)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return target

    def load(self, rule_id: str) -> ProfileSnapshot:
        raw = json.loads(self.path_for(rule_id).read_text())
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
            rule_id=raw["rule_id"],
            dataset=raw["dataset"],
            table=raw["table"],
            captured_at=raw["captured_at"],
            row_count=raw["row_count"],
            columns=columns,
        )

    def list_rule_ids(self) -> list[str]:
        return sorted(p.stem for p in self._root.glob("*.json"))
