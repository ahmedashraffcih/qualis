from __future__ import annotations

import importlib.util

import pytest

from qualis.adapters.postgres import sql_templates

"""Unit tests for the PostgreSQL adapter SQL templates and module structure.

These tests do NOT require a running PostgreSQL server. They verify:
- SQL templates contain the correct PostgreSQL-dialect syntax.
- SQL templates do not contain DuckDB-specific syntax.
- The adapter module can be imported and raises ImportError gracefully when
  psycopg is absent (handled by monkeypatching _PSYCOPG_AVAILABLE).
- Adapter wiring is correct using mock connections (skipped when psycopg absent).
"""

_PSYCOPG_INSTALLED = importlib.util.find_spec("psycopg") is not None

# ---------------------------------------------------------------------------
# SQL template — structural / dialect checks (always run, no psycopg needed)
# ---------------------------------------------------------------------------


class TestNotNullSqlTemplate:
    def test_contains_filter_where(self) -> None:
        assert "FILTER" in sql_templates.NOT_NULL_SQL
        assert "IS NULL" in sql_templates.NOT_NULL_SQL

    def test_uses_format_placeholder_for_column(self) -> None:
        assert '"{column}"' in sql_templates.NOT_NULL_SQL

    def test_uses_format_placeholder_for_table(self) -> None:
        assert "{table}" in sql_templates.NOT_NULL_SQL

    def test_no_duckdb_specific_syntax(self) -> None:
        assert "regexp_matches" not in sql_templates.NOT_NULL_SQL
        assert "$1" not in sql_templates.NOT_NULL_SQL
        assert "CAST(" not in sql_templates.NOT_NULL_SQL

    def test_selects_null_count_and_total_count(self) -> None:
        assert "null_count" in sql_templates.NOT_NULL_SQL
        assert "total_count" in sql_templates.NOT_NULL_SQL


class TestUniqueSqlTemplate:
    def test_contains_having_count_greater_than_one(self) -> None:
        assert "HAVING COUNT(*) > 1" in sql_templates.UNIQUE_SQL

    def test_uses_format_placeholder_for_column(self) -> None:
        assert '"{column}"' in sql_templates.UNIQUE_SQL

    def test_uses_format_placeholder_for_table(self) -> None:
        assert "{table}" in sql_templates.UNIQUE_SQL

    def test_selects_duplicate_count(self) -> None:
        assert "duplicate_count" in sql_templates.UNIQUE_SQL

    def test_no_duckdb_specific_syntax(self) -> None:
        assert "regexp_matches" not in sql_templates.UNIQUE_SQL
        assert "$1" not in sql_templates.UNIQUE_SQL

    def test_filters_nulls_from_uniqueness_check(self) -> None:
        assert "IS NOT NULL" in sql_templates.UNIQUE_SQL


class TestBetweenSqlTemplate:
    def test_uses_psycopg_param_style_for_min(self) -> None:
        assert "%(min)s" in sql_templates.BETWEEN_SQL

    def test_uses_psycopg_param_style_for_max(self) -> None:
        assert "%(max)s" in sql_templates.BETWEEN_SQL

    def test_uses_text_cast(self) -> None:
        assert "::text" in sql_templates.BETWEEN_SQL

    def test_selects_out_of_range_count_and_total_count(self) -> None:
        assert "out_of_range_count" in sql_templates.BETWEEN_SQL
        assert "total_count" in sql_templates.BETWEEN_SQL

    def test_no_duckdb_specific_syntax(self) -> None:
        assert "regexp_matches" not in sql_templates.BETWEEN_SQL
        assert "$1" not in sql_templates.BETWEEN_SQL
        # DuckDB template embeds values via {min_val}/{max_val}; PG uses %(min)s
        assert "{min_val}" not in sql_templates.BETWEEN_SQL
        assert "{max_val}" not in sql_templates.BETWEEN_SQL


class TestRegexSqlTemplate:
    def test_uses_tilde_operator_for_regex(self) -> None:
        # PostgreSQL POSIX regex match operator is ~; DuckDB uses regexp_matches
        assert "~ %(pattern)s" in sql_templates.REGEX_SQL

    def test_uses_psycopg_param_style_for_pattern(self) -> None:
        assert "%(pattern)s" in sql_templates.REGEX_SQL

    def test_uses_text_cast(self) -> None:
        assert "::text" in sql_templates.REGEX_SQL

    def test_no_regexp_matches(self) -> None:
        assert "regexp_matches" not in sql_templates.REGEX_SQL

    def test_no_positional_param_style(self) -> None:
        # DuckDB / SQLite use $1 / ? style; psycopg3 default is %(name)s
        assert "$1" not in sql_templates.REGEX_SQL
        assert "?" not in sql_templates.REGEX_SQL

    def test_selects_non_matching_count_and_total_count(self) -> None:
        assert "non_matching_count" in sql_templates.REGEX_SQL
        assert "total_count" in sql_templates.REGEX_SQL

    def test_null_values_excluded_from_non_matching_count(self) -> None:
        # The IS NOT NULL guard means nulls are not flagged as non-matching
        assert "IS NOT NULL" in sql_templates.REGEX_SQL


class TestTableExistsSqlTemplate:
    def test_uses_psycopg_param_style_for_schema(self) -> None:
        assert "%(schema)s" in sql_templates.TABLE_EXISTS_SQL

    def test_uses_psycopg_param_style_for_table(self) -> None:
        assert "%(table)s" in sql_templates.TABLE_EXISTS_SQL

    def test_queries_information_schema(self) -> None:
        assert "information_schema.tables" in sql_templates.TABLE_EXISTS_SQL

    def test_no_duckdb_specific_syntax(self) -> None:
        assert "regexp_matches" not in sql_templates.TABLE_EXISTS_SQL
        assert "$1" not in sql_templates.TABLE_EXISTS_SQL
        # DuckDB template embeds table name directly via '{table}'; PG uses params
        assert "'{table}'" not in sql_templates.TABLE_EXISTS_SQL


# ---------------------------------------------------------------------------
# Adapter class — import / instantiation tests (always run)
# ---------------------------------------------------------------------------


class TestPostgresAdapterImport:
    def test_adapter_module_imports_without_psycopg(self) -> None:
        """The adapter module must be importable even without psycopg installed.

        The try/except around psycopg sets _PSYCOPG_AVAILABLE = False so the
        import itself never raises; only instantiation does.
        """
        from qualis.adapters.postgres import adapter as pg_adapter

        assert hasattr(pg_adapter, "PostgresAdapter")

    def test_adapter_raises_import_error_when_psycopg_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When psycopg is not available, instantiation raises ImportError with
        a helpful message pointing to the install command."""
        from qualis.adapters.postgres import adapter as pg_adapter

        monkeypatch.setattr(pg_adapter, "_PSYCOPG_AVAILABLE", False)
        with pytest.raises(ImportError, match="psycopg"):
            pg_adapter.PostgresAdapter("postgresql://localhost/test")

    def test_import_error_message_includes_install_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from qualis.adapters.postgres import adapter as pg_adapter

        monkeypatch.setattr(pg_adapter, "_PSYCOPG_AVAILABLE", False)
        with pytest.raises(ImportError, match="qualis\\[postgres\\]"):
            pg_adapter.PostgresAdapter("postgresql://localhost/test")


# ---------------------------------------------------------------------------
# Adapter class — mock-based wiring tests (skipped when psycopg is absent)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PSYCOPG_INSTALLED, reason="psycopg not installed")
class TestPostgresAdapterWithMock:
    """Verify adapter wiring using a mock connection pool.

    These tests do not need a real PostgreSQL server. They confirm that
    the adapter correctly delegates to the pool and translates cursor
    results into dicts with lowercased column names.
    """

    def test_query_returns_list_of_dicts_with_lowercased_keys(self) -> None:
        from unittest.mock import MagicMock

        from qualis.adapters.postgres.adapter import PostgresAdapter

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_cur.description = [("Id",), ("Name",)]
        mock_cur.fetchall.return_value = [(1, "Alice")]

        adapter = PostgresAdapter.__new__(PostgresAdapter)
        adapter._pool = mock_pool  # type: ignore[attr-defined]

        rows = adapter.query("SELECT id, name FROM users")
        assert rows == [{"id": 1, "name": "Alice"}]

    def test_execute_returns_rowcount(self) -> None:
        from unittest.mock import MagicMock

        from qualis.adapters.postgres.adapter import PostgresAdapter

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 3

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        adapter = PostgresAdapter.__new__(PostgresAdapter)
        adapter._pool = mock_pool  # type: ignore[attr-defined]

        result = adapter.execute("DELETE FROM users WHERE active = false")
        assert result == 3


class TestStatementTimeout:
    """PR 2 runtime guard: SET LOCAL statement_timeout per check connection."""

    def _adapter_with_mock_pool(self, timeout_ms: int | None):
        from unittest.mock import MagicMock

        from qualis.adapters.postgres.adapter import PostgresAdapter

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (0, 0)

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        adapter = PostgresAdapter.__new__(PostgresAdapter)
        adapter._pool = mock_pool  # type: ignore[attr-defined]
        adapter._statement_timeout_ms = timeout_ms  # type: ignore[attr-defined]
        return adapter, mock_conn

    def test_check_emits_set_local_timeout_when_configured(self) -> None:
        adapter, mock_conn = self._adapter_with_mock_pool(timeout_ms=1500)
        adapter.check_not_null("public", "users", "email")
        executed = [str(c.args[0]) for c in mock_conn.execute.call_args_list]
        assert any("SET TRANSACTION READ ONLY" in s for s in executed)
        assert any("SET LOCAL statement_timeout = '1500ms'" in s for s in executed)

    def test_check_omits_timeout_when_not_configured(self) -> None:
        adapter, mock_conn = self._adapter_with_mock_pool(timeout_ms=None)
        adapter.check_not_null("public", "users", "email")
        executed = [str(c.args[0]) for c in mock_conn.execute.call_args_list]
        assert any("SET TRANSACTION READ ONLY" in s for s in executed)
        assert not any("statement_timeout" in s for s in executed)

    @pytest.mark.skipif(not _PSYCOPG_INSTALLED, reason="psycopg not installed")
    def test_init_accepts_statement_timeout_kwarg(self) -> None:
        import inspect

        from qualis.adapters.postgres.adapter import PostgresAdapter

        sig = inspect.signature(PostgresAdapter.__init__)
        assert "statement_timeout_ms" in sig.parameters


class TestFetchViolationSamples:
    """Optional sampling capability — mock-based, no live server."""

    def _adapter(self):
        from unittest.mock import MagicMock

        from qualis.adapters.postgres.adapter import PostgresAdapter

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("INVALID", "(0,3)")]

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        adapter = PostgresAdapter.__new__(PostgresAdapter)
        adapter._pool = mock_pool  # type: ignore[attr-defined]
        adapter._statement_timeout_ms = None  # type: ignore[attr-defined]
        return adapter, mock_cur

    def test_in_set_uses_any_param_and_ctid(self) -> None:
        adapter, mock_cur = self._adapter()
        samples = adapter.fetch_violation_samples(
            "public", "accidents", "severity_code", "in_set",
            {"values": ["FATAL", "MINOR"]}, 5,
        )
        sql, bind = mock_cur.execute.call_args.args
        assert "ctid::text" in sql
        assert "= ANY(%(values)s)" in sql
        assert "LIMIT %(limit)s" in sql
        assert bind["values"] == ["FATAL", "MINOR"]
        assert bind["limit"] == 5
        assert samples == [{"actual_value": "INVALID", "record_id": "(0,3)"}]

    def test_runs_inside_read_only_transaction(self) -> None:
        adapter, _ = self._adapter()
        mock_conn = adapter._pool.connection.return_value.__enter__.return_value  # type: ignore[attr-defined]
        adapter.fetch_violation_samples("public", "t", "c", "not_null", {}, 3)
        executed = [str(c.args[0]) for c in mock_conn.execute.call_args_list]
        assert any("SET TRANSACTION READ ONLY" in s for s in executed)

    def test_unsupported_kind_raises(self) -> None:
        adapter, _ = self._adapter()
        with pytest.raises(ValueError, match="unsupported sample kind"):
            adapter.fetch_violation_samples("public", "t", "c", "row_count", {}, 3)


class TestConditions:
    """Condition pushdown (AgDR-0005) via the bind-style SQL renderer."""

    def _adapter(self):
        from unittest.mock import MagicMock

        from qualis.adapters.postgres.adapter import PostgresAdapter

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (0, 0)
        mock_cur.fetchall.return_value = []

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        adapter = PostgresAdapter.__new__(PostgresAdapter)
        adapter._pool = mock_pool  # type: ignore[attr-defined]
        adapter._statement_timeout_ms = None  # type: ignore[attr-defined]
        return adapter, mock_cur

    def test_supports_conditions_flag(self) -> None:
        from qualis.adapters.postgres.adapter import PostgresAdapter

        assert PostgresAdapter.supports_conditions is True

    def test_condition_appends_where_with_binds(self) -> None:
        from qualis.domain.condition import parse_condition

        adapter, mock_cur = self._adapter()
        cond = parse_condition("status = 'active' AND amount > -10")
        adapter.check_not_null("public", "t", "c", condition=cond)
        sql, bind = mock_cur.execute.call_args.args
        assert 'WHERE ("status" = %(cond_0)s AND "amount" > %(cond_1)s)' in sql
        assert bind["cond_0"] == "active"
        assert bind["cond_1"] == -10

    def test_unique_condition_filters_inner_scan_and_total(self) -> None:
        from qualis.domain.condition import parse_condition

        adapter, mock_cur = self._adapter()
        mock_cur.fetchone.side_effect = [(0,), (0,)]
        adapter.check_unique("public", "t", "c", condition=parse_condition("x = 1"))
        first_sql = mock_cur.execute.call_args_list[0].args[0]
        second_sql = mock_cur.execute.call_args_list[1].args[0]
        assert 'AND "x" = %(cond_0)s' in first_sql  # inner population scan
        assert 'WHERE "x" = %(cond_0)s' in second_sql  # conditioned total

    def test_sampling_predicate_gains_condition(self) -> None:
        from qualis.domain.condition import parse_condition

        adapter, mock_cur = self._adapter()
        adapter.fetch_violation_samples(
            "public", "t", "c", "not_null", {}, 5,
            condition=parse_condition("region = 'EU'"),
        )
        sql, bind = mock_cur.execute.call_args.args
        assert 'AND ("region" = %(cond_0)s)' in sql
        assert bind["cond_0"] == "EU"
        assert bind["limit"] == 5
