from __future__ import annotations

from typing import TYPE_CHECKING, Any

import duckdb

from qualis.adapters.duckdb.sql_templates import (
    BETWEEN_SQL,
    IN_SET_SQL,
    NOT_NEGATIVE_SQL,
    NOT_NULL_SQL,
    REFERENCE_LOOKUP_SQL,
    REGEX_SQL,
    ROW_COUNT_SQL,
    TABLE_EXISTS_SQL,
    UNIQUE_SQL,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def _qualified(schema: str, table: str) -> str:
    """Return a qualified table reference for use inside SQL strings."""
    if schema:
        return f'"{schema}"."{table}"'
    return f'"{table}"'


class DuckDBAdapter:
    """DuckDB-backed implementation of ``DatabasePort``.

    Parameters
    ----------
    database:
        Path to a persistent DuckDB file, or ``":memory:"`` (default) for an
        in-process, session-only database.
    """

    def __init__(self, database: str = ":memory:") -> None:
        self._con = duckdb.connect(database)

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def register_csv(self, table_name: str, path: str) -> None:
        """Create a table from a CSV file using DuckDB's auto-detection."""
        self._con.execute(
            f'CREATE TABLE "{table_name}" AS SELECT * FROM read_csv_auto(\'{path}\')'
        )

    def register_parquet(self, table_name: str, path: str) -> None:
        """Create a table from a Parquet file."""
        self._con.execute(
            f'CREATE TABLE "{table_name}" AS SELECT * FROM read_parquet(\'{path}\')'
        )

    # ------------------------------------------------------------------
    # DatabasePort implementation
    # ------------------------------------------------------------------

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute *sql* and return a list of dicts keyed by column name."""
        rel = self._con.execute(sql)
        columns = [desc[0] for desc in rel.description or []]
        return [dict(zip(columns, row, strict=True)) for row in rel.fetchall()]

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute a DML statement; return the number of rows affected."""
        self._con.execute(sql)
        # DuckDB does not expose rowcount directly; return 0 as a safe default
        return 0

    def stream(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        chunk_size: int = 10_000,
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream query results in chunks of *chunk_size* rows."""
        rel = self._con.execute(sql)
        columns = [desc[0] for desc in rel.description or []]
        while True:
            rows = rel.fetchmany(chunk_size)
            if not rows:
                break
            yield [dict(zip(columns, row, strict=True)) for row in rows]

    def table_exists(self, schema: str, table: str) -> bool:
        """Return True when the named table is registered in the database."""
        result = self._con.execute(
            TABLE_EXISTS_SQL.format(table=table)
        ).fetchone()
        return bool(result and result[0] > 0)

    # ------------------------------------------------------------------
    # Check methods
    # ------------------------------------------------------------------

    def check_not_null(self, schema: str, table: str, column: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = NOT_NULL_SQL.format(column=column, table=table_ref)
        row = self._con.execute(sql).fetchone()
        null_count, total_count = (row[0], row[1]) if row else (0, 0)
        return {"null_count": int(null_count), "total_count": int(total_count)}

    def check_unique(self, schema: str, table: str, column: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = UNIQUE_SQL.format(column=column, table=table_ref)
        row = self._con.execute(sql).fetchone()
        if row is None:
            # No duplicate groups at all — zero duplicates
            total_row = self._con.execute(
                f"SELECT COUNT(*) FROM {table_ref}"
            ).fetchone()
            total = int(total_row[0]) if total_row else 0
            return {"duplicate_count": 0, "total_count": total}
        dup_count = int(row[0])
        # Re-query total so it is accurate regardless of UNIQUE_SQL shape
        total_row = self._con.execute(
            f"SELECT COUNT(*) FROM {table_ref}"
        ).fetchone()
        total = int(total_row[0]) if total_row else 0
        return {"duplicate_count": dup_count, "total_count": total}

    def check_between(
        self,
        schema: str,
        table: str,
        column: str,
        min_val: str,
        max_val: str,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = BETWEEN_SQL.format(
            column=column, table=table_ref, min_val=min_val, max_val=max_val
        )
        row = self._con.execute(sql).fetchone()
        out_of_range, total = (row[0], row[1]) if row else (0, 0)
        return {"out_of_range_count": int(out_of_range), "total_count": int(total)}

    def check_regex(
        self,
        schema: str,
        table: str,
        column: str,
        pattern: str,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = REGEX_SQL.format(column=column, table=table_ref, pattern=pattern)
        row = self._con.execute(sql).fetchone()
        non_matching, total = (row[0], row[1]) if row else (0, 0)
        return {"non_matching_count": int(non_matching), "total_count": int(total)}

    def check_in_set(
        self,
        schema: str,
        table: str,
        column: str,
        values: list[str],
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        escaped = [v.replace("'", "''") for v in values]
        value_list = ", ".join(f"'{v}'" for v in escaped)
        sql = IN_SET_SQL.format(column=column, table=table_ref, value_list=value_list)
        row = self._con.execute(sql).fetchone()
        invalid, total = (row[0], row[1]) if row else (0, 0)
        return {"invalid_count": int(invalid), "total_count": int(total)}

    def check_row_count(self, schema: str, table: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = ROW_COUNT_SQL.format(table=table_ref)
        row = self._con.execute(sql).fetchone()
        count = int(row[0]) if row else 0
        return {"row_count": count}

    def check_not_negative(self, schema: str, table: str, column: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = NOT_NEGATIVE_SQL.format(column=column, table=table_ref)
        row = self._con.execute(sql).fetchone()
        negative, total = (row[0], row[1]) if row else (0, 0)
        return {"negative_count": int(negative), "total_count": int(total)}

    def check_reference_lookup(
        self,
        schema: str,
        table: str,
        column: str,
        valid_values: list[str],
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        escaped = [v.replace("'", "''") for v in valid_values]
        value_list = ", ".join(f"'{v}'" for v in escaped) or "NULL"
        sql = REFERENCE_LOOKUP_SQL.format(
            column=column, table=table_ref, value_list=value_list,
        )
        row = self._con.execute(sql).fetchone()
        invalid, total = (row[0], row[1]) if row else (0, 0)
        return {"invalid_count": int(invalid), "total_count": int(total)}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._con.close()
