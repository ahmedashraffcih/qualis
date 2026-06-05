"""SQLAlchemy meta-adapter — one ``DatabasePort`` implementation, many engines.

Every check is built from SQLAlchemy **Core expressions** (no raw SQL
strings), so the same code targets any dialect SQLAlchemy 2.x speaks and is
injection-safe by construction (AgDR-0004, design-review condition C3).

Timeout honesty: this adapter does NOT implement
``statement_timeout_ms`` — per-statement timeouts are dialect-specific and
faking them would defeat the guard's purpose. See ``docs/adapters.md`` for
the per-adapter timeout matrix. Engines needing real timeouts should use a
native adapter (e.g. Postgres) or enforce limits server-side.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

try:
    import sqlalchemy as sa

    _SA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SA_AVAILABLE = False

if TYPE_CHECKING:
    from collections.abc import Iterator


class SQLAlchemyAdapter:
    """``DatabasePort`` implementation over a SQLAlchemy 2.x engine.

    Parameters
    ----------
    url:
        Any SQLAlchemy database URL (``sqlite:///...``,
        ``mysql+pymysql://...``, ``mssql+pyodbc://...``, ...). The matching
        DBAPI driver is user-supplied — qualis pins only ``sqlalchemy``
        itself (``pip install 'qualis[sqlalchemy]'``).
    engine:
        Optional pre-built engine (overrides *url*) for tests or custom
        pooling.
    """

    def __init__(self, url: str, *, engine: Any = None) -> None:
        if not _SA_AVAILABLE:
            raise ImportError(
                "sqlalchemy is required for SQLAlchemyAdapter. "
                "Install it with: pip install 'qualis[sqlalchemy]'"
            )
        self._engine = engine if engine is not None else sa.create_engine(url)
        if self._engine.dialect.name == "sqlite":
            self._install_sqlite_regexp()

    # ------------------------------------------------------------------
    # Engine helpers
    # ------------------------------------------------------------------

    def _install_sqlite_regexp(self) -> None:
        """SQLite ships no REGEXP function — install a Python one.

        Honest enablement for the one dialect that documents REGEXP as a
        user-supplied function; other dialects use their native operator
        via ``ColumnOperators.regexp_match``.
        """

        def _regexp(pattern: str, value: Any) -> bool:
            if value is None:
                return False
            return re.search(pattern, str(value)) is not None

        @sa.event.listens_for(self._engine, "connect")
        def _on_connect(dbapi_conn: Any, _record: Any) -> None:
            dbapi_conn.create_function("regexp", 2, _regexp)

    @staticmethod
    def _target(schema: str, table: str) -> Any:
        return sa.table(table, schema=schema or None)

    # ------------------------------------------------------------------
    # Generic DatabasePort surface
    # ------------------------------------------------------------------

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            result = conn.execute(sa.text(sql), params or {})
            return [dict(row) for row in result.mappings()]

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(sa.text(sql), params or {})
            return result.rowcount if result.rowcount is not None else 0

    def stream(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        chunk_size: int = 10_000,
    ) -> Iterator[list[dict[str, Any]]]:
        with self._engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(
                sa.text(sql), params or {}
            )
            while True:
                rows = result.mappings().fetchmany(chunk_size)
                if not rows:
                    break
                yield [dict(r) for r in rows]

    def table_exists(self, schema: str, table: str) -> bool:
        return bool(sa.inspect(self._engine).has_table(table, schema=schema or None))

    # ------------------------------------------------------------------
    # Check methods — Core expressions only
    # ------------------------------------------------------------------

    def _counts(self, stmt: Any) -> tuple[int, ...]:
        with self._engine.connect() as conn:
            row = conn.execute(stmt).one()
        return tuple(int(v or 0) for v in row)

    @staticmethod
    def _sum_case(predicate: Any) -> Any:
        # sum(case ...) instead of count(*) FILTER — FILTER is not
        # available on every dialect SQLAlchemy targets.
        return sa.func.coalesce(sa.func.sum(sa.case((predicate, 1), else_=0)), 0)

    def check_not_null(self, schema: str, table: str, column: str) -> dict[str, int]:
        c: sa.ColumnClause[Any] = sa.column(column)
        null_count, total = self._counts(
            sa.select(self._sum_case(c.is_(None)), sa.func.count())
            .select_from(self._target(schema, table))
        )
        return {"null_count": null_count, "total_count": total}

    def check_unique(self, schema: str, table: str, column: str) -> dict[str, int]:
        c: sa.ColumnClause[Any] = sa.column(column)
        # duplicate_count = non-null values minus distinct non-null values
        # ("extra copies" — matches the in-memory adapter's semantics).
        non_null, distinct, total = self._counts(
            sa.select(
                sa.func.count(c),
                sa.func.count(sa.distinct(c)),
                sa.func.count(),
            ).select_from(self._target(schema, table))
        )
        return {"duplicate_count": non_null - distinct, "total_count": total}

    def check_between(
        self,
        schema: str,
        table: str,
        column: str,
        min_val: str,
        max_val: str,
    ) -> dict[str, int]:
        c: sa.ColumnClause[Any] = sa.column(column)
        text_c = sa.cast(c, sa.String)
        out_pred = c.is_not(None) & ((text_c < min_val) | (text_c > max_val))
        out_count, total, checked = self._counts(
            sa.select(
                self._sum_case(out_pred),
                sa.func.count(),
                sa.func.count(c),
            ).select_from(self._target(schema, table))
        )
        return {"out_of_range_count": out_count, "total_count": total, "checked": checked}

    def check_regex(
        self,
        schema: str,
        table: str,
        column: str,
        pattern: str,
    ) -> dict[str, int]:
        c: sa.ColumnClause[Any] = sa.column(column)
        pred = c.is_not(None) & sa.not_(sa.cast(c, sa.String).regexp_match(pattern))
        non_matching, total = self._counts(
            sa.select(self._sum_case(pred), sa.func.count())
            .select_from(self._target(schema, table))
        )
        return {"non_matching_count": non_matching, "total_count": total}

    def check_in_set(
        self,
        schema: str,
        table: str,
        column: str,
        values: list[str],
    ) -> dict[str, int]:
        c: sa.ColumnClause[Any] = sa.column(column)
        pred = c.is_(None) | sa.cast(c, sa.String).notin_(values)
        invalid, total = self._counts(
            sa.select(self._sum_case(pred), sa.func.count())
            .select_from(self._target(schema, table))
        )
        return {"invalid_count": invalid, "total_count": total}

    def check_row_count(self, schema: str, table: str) -> dict[str, int]:
        (count,) = self._counts(
            sa.select(sa.func.count()).select_from(self._target(schema, table))
        )
        return {"row_count": count}

    def check_not_negative(self, schema: str, table: str, column: str) -> dict[str, int]:
        c: sa.ColumnClause[Any] = sa.column(column)
        negative, total = self._counts(
            sa.select(self._sum_case(c.is_not(None) & (c < 0)), sa.func.count())
            .select_from(self._target(schema, table))
        )
        return {"negative_count": negative, "total_count": total}

    def check_reference_lookup(
        self,
        schema: str,
        table: str,
        column: str,
        valid_values: list[str],
    ) -> dict[str, int]:
        c: sa.ColumnClause[Any] = sa.column(column)
        pred = c.is_not(None) & sa.cast(c, sa.String).notin_(valid_values)
        invalid, total = self._counts(
            sa.select(self._sum_case(pred), sa.func.count())
            .select_from(self._target(schema, table))
        )
        return {"invalid_count": invalid, "total_count": total}

    # ------------------------------------------------------------------
    # Optional sampling capability (AgDR-0003)
    # ------------------------------------------------------------------

    def fetch_violation_samples(
        self,
        schema: str,
        table: str,
        column: str,
        kind: str,
        params: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Up to *limit* failing rows as evidence — Core predicates mirror
        the count expressions above, so samples are members of the counted
        set. ``record_id`` is a 1-based ``row_number()``."""
        c: sa.ColumnClause[Any] = sa.column(column)
        target = self._target(schema, table)
        subq = (
            sa.select(
                c.label("actual_value"),
                sa.func.row_number().over().label("rid"),
            )
            .select_from(target)
            .subquery()
        )
        v = subq.c.actual_value
        text_v = sa.cast(v, sa.String)

        pred: sa.ColumnElement[bool]
        if kind == "not_null":
            pred = v.is_(None)
        elif kind == "unique":
            dups = (
                sa.select(c)
                .select_from(target)
                .where(c.is_not(None))
                .group_by(c)
                .having(sa.func.count() > 1)
            )
            pred = v.is_not(None) & v.in_(dups)
        elif kind == "between":
            pred = v.is_not(None) & (
                (text_v < params["min"]) | (text_v > params["max"])
            )
        elif kind == "regex":
            pred = v.is_not(None) & sa.not_(text_v.regexp_match(params["pattern"]))
        elif kind == "in_set":
            pred = v.is_(None) | text_v.notin_(list(params["values"]))
        elif kind == "not_negative":
            pred = v.is_not(None) & (v < 0)
        elif kind == "reference_lookup":
            pred = v.is_not(None) & text_v.notin_(list(params["valid_values"]))
        else:
            raise ValueError(f"unsupported sample kind: {kind!r}")

        stmt = sa.select(subq.c.actual_value, subq.c.rid).where(pred).limit(int(limit))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [{"actual_value": r[0], "record_id": r[1]} for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Dispose the engine's connection pool."""
        self._engine.dispose()
