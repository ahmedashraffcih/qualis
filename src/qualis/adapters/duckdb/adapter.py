from __future__ import annotations

from typing import TYPE_CHECKING, Any

import duckdb

from qualis.adapters._condition_sql import render_sql_condition
from qualis.adapters.duckdb.sql_templates import (
    BETWEEN_SQL,
    IN_SET_SQL,
    NOT_NEGATIVE_SQL,
    NOT_NULL_SQL,
    REFERENCE_LOOKUP_SQL,
    REGEX_SQL,
    ROW_COUNT_SQL,
    TABLE_EXISTS_SQL,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from qualis.domain.condition import ConditionExpr


def _qualified(schema: str, table: str) -> str:
    """Return a qualified table reference for use inside SQL strings."""
    if schema:
        return f'"{schema}"."{table}"'
    return f'"{table}"'


class DuckDBAdapter:
    #: Conditioned rules are honoured (AgDR-0005) via the literal-style
    #: SQL renderer — safe because the fragment's value space is the
    #: parsed grammar's, never raw user text.
    supports_conditions = True

    """DuckDB-backed implementation of ``DatabasePort``.

    Parameters
    ----------
    database:
        Path to a persistent DuckDB file, or ``":memory:"`` (default) for an
        in-process, session-only database.

    Notes
    -----
    DuckDB has no per-statement timeout, so ``QualisSettings.statement_timeout_ms``
    does not apply here. For runaway-query protection use OS-level limits or
    run checks against a remote engine that supports timeouts (e.g. Postgres).
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


    @staticmethod
    def _where(condition: ConditionExpr | None, *, prefix: str = " WHERE ") -> str:
        if condition is None:
            return ""
        fragment, _ = render_sql_condition(condition, "literal")
        return f"{prefix}{fragment}"

    # ------------------------------------------------------------------
    # Check methods
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
        sql += self._where(condition)
        row = self._con.execute(sql).fetchone()
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
        where = self._where(condition)
        # Condition applies to the inner population scan (the review's
        # HAVING-subquery trap, AgDR-0005) and to the total.
        sql = (
            "SELECT COUNT(*) AS duplicate_count FROM ("
            f'  SELECT "{column}" FROM {table_ref}{where} '
            f'  GROUP BY "{column}" HAVING COUNT(*) > 1'
            ") dup"
        )
        row = self._con.execute(sql).fetchone()
        dup_count = int(row[0]) if row else 0
        total_row = self._con.execute(
            f"SELECT COUNT(*) FROM {table_ref}{where}"
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
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = BETWEEN_SQL.format(
            column=column, table=table_ref, min_val=min_val, max_val=max_val
        )
        sql += self._where(condition)
        row = self._con.execute(sql).fetchone()
        out_of_range, total = (row[0], row[1]) if row else (0, 0)
        return {"out_of_range_count": int(out_of_range), "total_count": int(total)}

    def check_regex(
        self,
        schema: str,
        table: str,
        column: str,
        pattern: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = REGEX_SQL.format(column=column, table=table_ref, pattern=pattern)
        sql += self._where(condition)
        row = self._con.execute(sql).fetchone()
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
        escaped = [v.replace("'", "''") for v in values]
        value_list = ", ".join(f"'{v}'" for v in escaped)
        sql = IN_SET_SQL.format(column=column, table=table_ref, value_list=value_list)
        sql += self._where(condition)
        row = self._con.execute(sql).fetchone()
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
        sql += self._where(condition)
        row = self._con.execute(sql).fetchone()
        count = int(row[0]) if row else 0
        return {"row_count": count}

    def check_not_negative(
        self,
        schema: str,
        table: str,
        column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        sql = NOT_NEGATIVE_SQL.format(column=column, table=table_ref)
        sql += self._where(condition)
        row = self._con.execute(sql).fetchone()
        negative, total = (row[0], row[1]) if row else (0, 0)
        return {"negative_count": int(negative), "total_count": int(total)}

    def check_reference_lookup(
        self,
        schema: str,
        table: str,
        column: str,
        valid_values: list[str],
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        table_ref = _qualified(schema, table)
        escaped = [v.replace("'", "''") for v in valid_values]
        value_list = ", ".join(f"'{v}'" for v in escaped) or "NULL"
        sql = REFERENCE_LOOKUP_SQL.format(
            column=column, table=table_ref, value_list=value_list,
        )
        sql += self._where(condition)
        row = self._con.execute(sql).fetchone()
        invalid, total = (row[0], row[1]) if row else (0, 0)
        return {"invalid_count": int(invalid), "total_count": int(total)}

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
        """JOIN-mode reference lookup (AgDR-0006).

        Capability contract: NULL-safe ``NOT EXISTS`` correlated subquery —
        never ``NOT IN (subquery)``, whose three-valued logic zeroes the
        invalid count the moment the reference key contains a NULL (review
        condition C1). Outer FROM contains only the aliased target ``t``,
        so unqualified condition columns bind to the target (C2).
        """
        table_ref = _qualified(schema, table)
        ref_ref = _qualified(reference_schema, reference)
        where = self._where(condition)
        sql = (
            "SELECT COALESCE(SUM(CASE WHEN "
            f't."{column}" IS NOT NULL AND NOT EXISTS ('
            f'SELECT 1 FROM {ref_ref} r WHERE r."{key_column}" = t."{column}"'
            ") THEN 1 ELSE 0 END), 0) AS invalid_count, "
            "COUNT(*) AS total_count "
            f"FROM {table_ref} AS t{where}"
        )
        row = self._con.execute(sql).fetchone()
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

        Each predicate mirrors the corresponding check template in
        ``sql_templates`` so sampled rows are members of the counted set.
        ``record_id`` is a 1-based row number (works on registered CSV /
        parquet views, where ``rowid`` does not exist).
        """

        def esc(value: str) -> str:
            return value.replace("'", "''")

        def value_list(values: list[str]) -> str:
            return ", ".join(f"'{esc(v)}'" for v in values) or "NULL"

        table_ref = _qualified(schema, table)
        if kind == "not_null":
            predicate = "actual_value IS NULL"
        elif kind == "unique":
            inner_condition = self._where(condition, prefix=" AND ")
            predicate = (
                "actual_value IS NOT NULL AND actual_value IN ("
                f'SELECT "{column}" FROM {table_ref} '
                f'WHERE "{column}" IS NOT NULL{inner_condition} '
                f'GROUP BY "{column}" HAVING COUNT(*) > 1)'
            )
        elif kind == "between":
            predicate = (
                f"CAST(actual_value AS VARCHAR) < '{esc(params['min'])}' "
                f"OR CAST(actual_value AS VARCHAR) > '{esc(params['max'])}'"
            )
        elif kind == "regex":
            predicate = (
                "actual_value IS NULL OR NOT regexp_matches("
                f"CAST(actual_value AS VARCHAR), '{esc(params['pattern'])}')"
            )
        elif kind == "in_set":
            predicate = (
                "actual_value IS NULL OR CAST(actual_value AS VARCHAR) "
                f"NOT IN ({value_list(params['values'])})"
            )
        elif kind == "not_negative":
            predicate = "actual_value IS NOT NULL AND actual_value < 0"
        elif kind == "reference_lookup":
            predicate = (
                "actual_value IS NOT NULL AND CAST(actual_value AS VARCHAR) "
                f"NOT IN ({value_list(params['valid_values'])})"
            )
        elif kind == "reference_join":
            ref_ref = _qualified(
                str(params["reference_schema"]), str(params["reference"])
            )
            key = str(params["key_column"])
            predicate = (
                "actual_value IS NOT NULL AND NOT EXISTS ("
                f'SELECT 1 FROM {ref_ref} r WHERE r."{key}" = actual_value)'
            )
        else:
            raise ValueError(f"unsupported sample kind: {kind!r}")

        where = self._where(condition)
        sql = (
            "SELECT actual_value, rid FROM ("
            f'SELECT "{column}" AS actual_value, row_number() OVER () AS rid '
            f"FROM {table_ref}{where}) q WHERE {predicate} LIMIT {int(limit)}"
        )
        rows = self._con.execute(sql).fetchall()
        return [{"actual_value": r[0], "record_id": r[1]} for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._con.close()
