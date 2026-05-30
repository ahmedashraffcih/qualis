"""Statistical table profiler — produces column/table profiles via aggregate SQL.

Pure deterministic profiling. No LLM. No external API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ColumnProfile:
    """Aggregate statistics for a single column."""

    name: str
    inferred_type: str
    total_count: int
    null_count: int
    null_fraction: float
    distinct_count: int
    distinct_fraction: float
    min_value: str | None
    max_value: str | None
    sample_values: list[str] = field(default_factory=list)
    is_likely_id: bool = False


@dataclass(frozen=True)
class TableProfile:
    """Aggregate profile for a table."""

    table: str
    row_count: int
    columns: list[ColumnProfile]


_ID_NAME_PATTERN = re.compile(r"(^|_)id$", re.IGNORECASE)


def _normalize_type(duckdb_type: str) -> str:
    """Map a DuckDB column type to one of the inferred-type categories."""
    t = duckdb_type.upper()
    if any(k in t for k in ("INT", "DECIMAL", "NUMERIC", "DOUBLE", "REAL", "FLOAT", "HUGEINT")):
        if "INT" in t and "FLOAT" not in t and "DOUBLE" not in t:
            return "integer"
        return "float"
    if any(k in t for k in ("DATE", "TIMESTAMP", "TIME")):
        return "date"
    if "BOOL" in t:
        return "boolean"
    return "string"


def _numeric_types() -> set[str]:
    return {"integer", "float"}


def profile_table(adapter: Any, table: str) -> TableProfile:
    """Profile a table using SQL aggregates run via the adapter.

    The adapter must expose a DuckDB-compatible ``query(sql)`` method (the
    in-process DuckDBAdapter is the primary target).
    """
    quoted_table = f'"{table}"'

    columns_meta = adapter.query(f"DESCRIBE {quoted_table}")
    if not columns_meta:
        return TableProfile(table=table, row_count=0, columns=[])

    count_rows = adapter.query(f"SELECT COUNT(*) AS c FROM {quoted_table}")
    row_count = int(count_rows[0]["c"]) if count_rows else 0

    columns: list[ColumnProfile] = []
    for meta in columns_meta:
        col_name = str(meta.get("column_name") or meta.get("Field") or "")
        col_type = str(meta.get("column_type") or meta.get("Type") or "")
        if not col_name:
            continue
        inferred = _normalize_type(col_type)
        columns.append(_profile_column(adapter, table, col_name, inferred, row_count))

    return TableProfile(table=table, row_count=row_count, columns=columns)


def _profile_column(
    adapter: Any,
    table: str,
    column: str,
    inferred_type: str,
    row_count: int,
) -> ColumnProfile:
    quoted_table = f'"{table}"'
    quoted_col = f'"{column}"'

    sql = (
        f"SELECT "
        f"  COUNT(*) FILTER (WHERE {quoted_col} IS NULL) AS null_count, "
        f"  COUNT(DISTINCT {quoted_col}) AS distinct_count, "
        f"  MIN(CAST({quoted_col} AS VARCHAR)) AS min_v, "
        f"  MAX(CAST({quoted_col} AS VARCHAR)) AS max_v "
        f"FROM {quoted_table}"
    )
    rows = adapter.query(sql)
    if not rows:
        return ColumnProfile(
            name=column,
            inferred_type=inferred_type,
            total_count=row_count,
            null_count=0,
            null_fraction=0.0,
            distinct_count=0,
            distinct_fraction=0.0,
            min_value=None,
            max_value=None,
            sample_values=[],
        )

    stats = rows[0]
    null_count = int(stats["null_count"])
    distinct = int(stats["distinct_count"])
    min_v = stats["min_v"]
    max_v = stats["max_v"]

    null_fraction = (null_count / row_count) if row_count else 0.0
    non_null = row_count - null_count
    distinct_fraction = (distinct / non_null) if non_null else 0.0

    sample_rows = adapter.query(
        f"SELECT DISTINCT CAST({quoted_col} AS VARCHAR) AS v FROM {quoted_table} "
        f"WHERE {quoted_col} IS NOT NULL LIMIT 10"
    )
    samples = [str(r["v"]) for r in sample_rows]

    is_likely_id = bool(_ID_NAME_PATTERN.search(column)) or (
        non_null > 0 and distinct_fraction >= 0.99
    )

    return ColumnProfile(
        name=column,
        inferred_type=inferred_type,
        total_count=row_count,
        null_count=null_count,
        null_fraction=null_fraction,
        distinct_count=distinct,
        distinct_fraction=distinct_fraction,
        min_value=str(min_v) if min_v is not None else None,
        max_value=str(max_v) if max_v is not None else None,
        sample_values=samples,
        is_likely_id=is_likely_id,
    )
