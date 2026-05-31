"""Load DatasetContext from context.yaml files."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003  (used at runtime)
from typing import Any

import yaml

from qualis.domain.context import (
    ColumnContext,
    DatasetContext,
    SentinelDeclaration,
)


def load_context_from_file(path: Path) -> DatasetContext:
    """Load a DatasetContext from a YAML file.

    Schema (all fields except ``dataset`` optional)::

        dataset: <name>
        business_grain: <free text, optional>
        columns:
          <column_name>:
            sentinels:
              - value: <str>
                meaning: <str>
            exceptions: [<str>, ...]
            notes: <str>

    Raises
    ------
    FileNotFoundError
        Path doesn't exist.
    ValueError
        Schema is malformed (missing ``dataset``).
    """
    if not path.exists():
        raise FileNotFoundError(f"Context file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    if "dataset" not in raw:
        raise ValueError(f"Context file {path} is missing required field 'dataset'")

    columns = {
        name: _parse_column(name, raw_col)
        for name, raw_col in (raw.get("columns") or {}).items()
    }

    return DatasetContext(
        dataset=str(raw["dataset"]),
        business_grain=raw.get("business_grain"),
        columns=columns,
    )


def _parse_column(name: str, raw: dict[str, Any]) -> ColumnContext:
    sentinels = [
        SentinelDeclaration(value=str(s["value"]), meaning=str(s.get("meaning", "")))
        for s in (raw.get("sentinels") or [])
    ]
    return ColumnContext(
        column=name,
        sentinels=sentinels,
        exceptions=list(raw.get("exceptions") or []),
        notes=str(raw.get("notes", "")),
    )
