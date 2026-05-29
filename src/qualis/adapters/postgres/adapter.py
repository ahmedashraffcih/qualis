from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import psycopg_pool  # type: ignore[import-not-found]

    _PSYCOPG_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PSYCOPG_AVAILABLE = False

from qualis.adapters.postgres.sql_templates import (
    BETWEEN_SQL,
    IN_SET_SQL,
    NOT_NEGATIVE_SQL,
    NOT_NULL_SQL,
    REGEX_SQL,
    ROW_COUNT_SQL,
    TABLE_EXISTS_SQL,
    UNIQUE_SQL,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def _qualified(schema: str, table: str) -> str:
    """Return a double-quoted, schema-qualified table reference."""
    if schema:
        return f'"{schema}"."{table}"'
    return f'"{table}"'


def _rows_as_dicts(cursor: Any) -> list[dict[str, Any]]:
    """Convert cursor results to a list of dicts with lowercased column names."""
    if cursor.description is None:
        return []
    columns = [desc[0].lower() for desc in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


class PostgresAdapter:
    """PostgreSQL-backed implementation of ``DatabasePort``.

    Requires the ``psycopg[binary]`` and ``psycopg-pool`` optional dependencies
    (install with ``pip install 'qualis[postgres]'``).

    All data-quality check queries are executed inside a ``READ ONLY``
    transaction to prevent accidental mutations on the target database.

    Parameters
    ----------
    connection_url:
        A libpq connection string or PostgreSQL URI
        (e.g. ``postgresql://user:pass@host/dbname``).
    min_size:
        Minimum number of connections kept alive in the pool.
    max_size:
        Maximum number of connections the pool will open.
    """

    def __init__(
        self,
        connection_url: str,
        min_size: int = 1,
        max_size: int = 5,
    ) -> None:
        if not _PSYCOPG_AVAILABLE:
            raise ImportError(
                "psycopg and psycopg-pool are required for PostgresAdapter. "
                "Install them with: pip install 'qualis[postgres]'"
            )
        self._pool: Any = psycopg_pool.ConnectionPool(
            connection_url,
            min_size=min_size,
            max_size=max_size,
            open=True,
        )

    # ------------------------------------------------------------------
    # DatabasePort implementation
    # ------------------------------------------------------------------

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute *sql* and return a list of dicts keyed by lowercased column name."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return _rows_as_dicts(cur)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute a DML statement; return the number of rows affected."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount if cur.rowcount is not None else 0

    def stream(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        chunk_size: int = 10_000,
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream query results using a server-side cursor, yielding *chunk_size* rows at a time."""
        with self._pool.connection() as conn, conn.cursor(name="qualis_stream") as cur:
            cur.execute(sql, params)
            columns = (
                [desc[0].lower() for desc in cur.description]
                if cur.description
                else []
            )
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break
                yield [dict(zip(columns, row, strict=True)) for row in rows]

    def table_exists(self, schema: str, table: str) -> bool:
        """Return True when the named table exists in ``information_schema``."""
        schema_name = schema if schema else "public"
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(TABLE_EXISTS_SQL, {"schema": schema_name, "table": table})
            row = cur.fetchone()
        return bool(row and row[0] > 0)

    # ------------------------------------------------------------------
    # Check methods — all run inside a READ ONLY transaction
    # ------------------------------------------------------------------

    def check_not_null(self, schema: str, table: str, column: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = NOT_NULL_SQL.format(column=column, table=table_ref)
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        null_count, total_count = (row[0], row[1]) if row else (0, 0)
        return {"null_count": int(null_count), "total_count": int(total_count)}

    def check_unique(self, schema: str, table: str, column: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = UNIQUE_SQL.format(column=column, table=table_ref)
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
                dup_count = int(row[0]) if row else 0
                # Re-query total so it is accurate regardless of UNIQUE_SQL shape
                cur.execute(f"SELECT COUNT(*) FROM {table_ref}")
                total_row = cur.fetchone()
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
        sql = BETWEEN_SQL.format(column=column, table=table_ref)
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, {"min": min_val, "max": max_val})
                row = cur.fetchone()
        out_of_range, total, checked = (row[0], row[1], row[2]) if row else (0, 0, 0)
        return {
            "out_of_range_count": int(out_of_range),
            "total_count": int(total),
            "checked": int(checked),
        }

    def check_regex(
        self,
        schema: str,
        table: str,
        column: str,
        pattern: str,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = REGEX_SQL.format(column=column, table=table_ref)
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, {"pattern": pattern})
                row = cur.fetchone()
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
        sql = IN_SET_SQL.format(column=column, table=table_ref)
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql, {"values": values})
                row = cur.fetchone()
        invalid, total = (row[0], row[1]) if row else (0, 0)
        return {"invalid_count": int(invalid), "total_count": int(total)}

    def check_row_count(self, schema: str, table: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = ROW_COUNT_SQL.format(table=table_ref)
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        count = int(row[0]) if row else 0
        return {"row_count": count}

    def check_not_negative(self, schema: str, table: str, column: str) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = NOT_NEGATIVE_SQL.format(column=column, table=table_ref)
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        negative, total = (row[0], row[1]) if row else (0, 0)
        return {"negative_count": int(negative), "total_count": int(total)}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.close()
