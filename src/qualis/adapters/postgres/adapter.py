from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    # ``psycopg_pool`` ships type stubs in some versions but not others,
    # and is only installed when the [postgres] extra is selected. Suppress
    # both "can't find stubs" (env without extra) and "unused ignore"
    # (env with extra and stubs available) to keep mypy happy in both.
    import psycopg_pool  # type: ignore[import-not-found, unused-ignore]

    _PSYCOPG_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PSYCOPG_AVAILABLE = False

from qualis.adapters._condition_sql import render_sql_condition
from qualis.adapters.postgres.sql_templates import (
    AGGREGATE_ROW_COUNT_SQL,
    AGGREGATE_SUM_SQL,
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

    from qualis.domain.condition import ConditionExpr


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
    #: Conditioned rules are honoured (AgDR-0005) via the bind-style SQL
    #: renderer (values always travel as psycopg named parameters).
    supports_conditions = True

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
        statement_timeout_ms: int | None = None,
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
        # Per-statement server-side timeout applied to every check query via
        # SET LOCAL (scoped to the transaction, so pooled connections are not
        # permanently altered). None = no timeout (server default).
        self._statement_timeout_ms = statement_timeout_ms

    def _begin_read_only(self, conn: Any) -> None:
        """Mark the transaction READ ONLY and apply the statement timeout.

        ``SET LOCAL`` scopes the timeout to the current transaction — the
        pooled connection comes back clean for the next borrower.
        """
        conn.execute("SET TRANSACTION READ ONLY")
        if self._statement_timeout_ms is not None:
            conn.execute(
                f"SET LOCAL statement_timeout = '{int(self._statement_timeout_ms)}ms'"
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


    @staticmethod
    def _where(
        condition: ConditionExpr | None, *, prefix: str = " WHERE "
    ) -> tuple[str, dict[str, Any]]:
        if condition is None:
            return "", {}
        fragment, binds = render_sql_condition(condition, "bind")
        return f"{prefix}{fragment}", binds

    # ------------------------------------------------------------------
    # Check methods — all run inside a READ ONLY transaction
    # ------------------------------------------------------------------

    def check_not_null(
        self,
        schema: str,
        table: str,
        column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = NOT_NULL_SQL.format(column=column, table=table_ref)
        where, binds = self._where(condition)
        sql += where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                row = cur.fetchone()
        null_count, total_count = (row[0], row[1]) if row else (0, 0)
        return {"null_count": int(null_count), "total_count": int(total_count)}

    def check_unique(
        self,
        schema: str,
        table: str,
        column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = UNIQUE_SQL.format(column=column, table=table_ref)
        # Inner population scan already has WHERE IS NOT NULL — the condition
        # joins it with AND (the review's HAVING-subquery trap, AgDR-0005).
        inner, binds = self._where(condition, prefix=" AND ")
        sql = sql.replace('IS NOT NULL\n', f'IS NOT NULL{inner}\n', 1)
        total_where, total_binds = self._where(condition)
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                row = cur.fetchone()
                dup_count = int(row[0]) if row else 0
                # Re-query total so it is accurate regardless of UNIQUE_SQL shape
                cur.execute(
                    f"SELECT COUNT(*) FROM {table_ref}{total_where}", total_binds
                )
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
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = BETWEEN_SQL.format(column=column, table=table_ref)
        where, binds = self._where(condition)
        sql = sql.rstrip() + where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, {"min": min_val, "max": max_val, **binds})
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
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = REGEX_SQL.format(column=column, table=table_ref)
        where, binds = self._where(condition)
        sql = sql.rstrip() + where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, {"pattern": pattern, **binds})
                row = cur.fetchone()
        non_matching, total = (row[0], row[1]) if row else (0, 0)
        return {"non_matching_count": int(non_matching), "total_count": int(total)}

    def check_in_set(
        self,
        schema: str,
        table: str,
        column: str,
        values: list[str],
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = IN_SET_SQL.format(column=column, table=table_ref)
        where, binds = self._where(condition)
        sql = sql.rstrip() + where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, {"values": values, **binds})
                row = cur.fetchone()
        invalid, total = (row[0], row[1]) if row else (0, 0)
        return {"invalid_count": int(invalid), "total_count": int(total)}

    def check_row_count(
        self,
        schema: str,
        table: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = ROW_COUNT_SQL.format(table=table_ref)
        where, binds = self._where(condition)
        # ROW_COUNT_SQL ends with a newline — keep WHERE on the same statement
        sql = sql.rstrip() + where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                row = cur.fetchone()
        count = int(row[0]) if row else 0
        return {"row_count": count}

    def check_aggregate(
        self,
        schema: str,
        table: str,
        metric: str,
        column: str | None = None,
        condition: ConditionExpr | None = None,
    ) -> dict[str, Any]:
        """Aggregate capability for cross_dataset_assertion (AgDR-0008).

        Fixed metric→template map — the metric name is never formatted
        into SQL. ``::numeric`` returns Decimal for ``sum`` so the
        engine's tolerance comparison keeps exact precision. Runs in its
        own transaction; the per-statement timeout bounds this leg alone.
        """
        if metric == "row_count":
            sql = AGGREGATE_ROW_COUNT_SQL.format(table=_qualified(schema, table))
        elif metric == "sum":
            if not column:
                raise ValueError("check_aggregate: metric 'sum' requires a column")
            sql = AGGREGATE_SUM_SQL.format(
                table=_qualified(schema, table), column=column
            )
        else:
            raise ValueError(f"check_aggregate: unsupported metric {metric!r}")
        where, binds = self._where(condition)
        sql = sql.rstrip() + where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                row = cur.fetchone()
        return {"value": row[0] if row else None}

    def check_not_negative(
        self,
        schema: str,
        table: str,
        column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = NOT_NEGATIVE_SQL.format(column=column, table=table_ref)
        where, binds = self._where(condition)
        sql += where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                row = cur.fetchone()
        negative, total = (row[0], row[1]) if row else (0, 0)
        return {"negative_count": int(negative), "total_count": int(total)}

    def check_reference_join(
        self,
        schema: str,
        table: str,
        column: str,
        reference_schema: str,
        reference: str,
        key_column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        """JOIN-mode reference lookup (AgDR-0006) — NULL-safe NOT EXISTS
        (capability contract, review condition C1); outer FROM is only the
        aliased target so condition columns bind to ``t`` (C2)."""
        table_ref = _qualified(schema, table)
        ref_ref = _qualified(reference_schema, reference)
        where, binds = self._where(condition)
        sql = (
            "SELECT COALESCE(SUM(CASE WHEN "
            f't."{column}" IS NOT NULL AND NOT EXISTS ('
            f'SELECT 1 FROM {ref_ref} r WHERE r."{key_column}" = t."{column}"'
            ") THEN 1 ELSE 0 END), 0) AS invalid_count, "
            "COUNT(*) AS total_count "
            f"FROM {table_ref} AS t{where}"
        )
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                row = cur.fetchone()
        invalid, total = (row[0], row[1]) if row else (0, 0)
        return {"invalid_count": int(invalid), "total_count": int(total)}

    def fetch_violation_samples(
        self,
        schema: str,
        table: str,
        column: str,
        kind: str,
        params: dict[str, Any],
        limit: int,
        condition: ConditionExpr | None = None,
    ) -> list[dict[str, Any]]:
        """Optional capability: return up to *limit* failing rows as evidence.

        Predicates mirror the count templates in ``sql_templates`` so sampled
        rows are members of the counted set. ``record_id`` is the row's
        ``ctid`` (physical locator — stable within the sampling query, not
        across VACUUM; good enough for evidence display).
        """
        bind: dict[str, Any] = {"limit": limit}
        if kind == "not_null":
            predicate = '"{column}" IS NULL'
        elif kind == "unique":
            predicate = (
                '"{column}" IS NOT NULL AND "{column}" IN ('
                'SELECT "{column}" FROM {table} WHERE "{column}" IS NOT NULL '
                'GROUP BY "{column}" HAVING COUNT(*) > 1)'
            )
        elif kind == "between":
            predicate = (
                '"{column}" IS NOT NULL AND '
                '("{column}"::text < %(min)s OR "{column}"::text > %(max)s)'
            )
            bind.update({"min": params["min"], "max": params["max"]})
        elif kind == "regex":
            predicate = (
                '"{column}" IS NOT NULL AND NOT ("{column}"::text ~ %(pattern)s)'
            )
            bind["pattern"] = params["pattern"]
        elif kind == "in_set":
            predicate = (
                '"{column}" IS NULL OR NOT ("{column}"::text = ANY(%(values)s))'
            )
            bind["values"] = list(params["values"])
        elif kind == "not_negative":
            predicate = '"{column}" IS NOT NULL AND "{column}" < 0'
        elif kind == "reference_lookup":
            predicate = (
                '"{column}" IS NOT NULL AND '
                'NOT ("{column}"::text = ANY(%(valid_values)s))'
            )
            bind["valid_values"] = list(params["valid_values"])
        elif kind == "reference_join":
            ref_ref = _qualified(
                str(params["reference_schema"]), str(params["reference"])
            )
            key = str(params["key_column"])
            predicate = (
                '"{column}" IS NOT NULL AND NOT EXISTS ('
                f'SELECT 1 FROM {ref_ref} r WHERE r."{key}" = ' + '"{column}")'
            )
        else:
            raise ValueError(f"unsupported sample kind: {kind!r}")

        table_ref = _qualified(schema, table)
        cond_clause, cond_binds = self._where(condition, prefix=" AND (")
        if cond_clause:
            cond_clause += ")"
        bind.update(cond_binds)
        sql = (
            'SELECT "{column}" AS actual_value, ctid::text AS rid '
            "FROM {table} WHERE " + predicate + cond_clause + " LIMIT %(limit)s"
        ).format(column=column, table=table_ref)
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, bind)
                rows = cur.fetchall()
        return [{"actual_value": r[0], "record_id": r[1]} for r in rows]

    def check_reference_lookup(
        self,
        schema: str,
        table: str,
        column: str,
        valid_values: list[str],
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = REFERENCE_LOOKUP_SQL.format(column=column, table=table_ref)
        where, binds = self._where(condition)
        sql = sql.rstrip() + where
        with self._pool.connection() as conn:
            self._begin_read_only(conn)
            with conn.cursor() as cur:
                cur.execute(sql, {"valid_values": valid_values, **binds})
                row = cur.fetchone()
        invalid, total = (row[0], row[1]) if row else (0, 0)
        return {"invalid_count": int(invalid), "total_count": int(total)}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.close()
