"""Render a condition AST to a SQL fragment for string-templated adapters.

Two styles, matching each adapter's existing parameter discipline:

- ``bind``    — psycopg named binds (``%(cond_0)s``) + a params dict
- ``literal`` — values inlined with single-quote doubling (DuckDB has no
  bind path; safe here because the input is the parsed AST, whose value
  space is the grammar's, never raw user text — AgDR-0005)

Identifiers are always double-quoted (review condition C4), so
reserved-word columns work on both engines.
"""

from __future__ import annotations

from typing import Any, Literal

from qualis.domain.condition import (
    And,
    Comparison,
    ConditionExpr,
    InList,
    IsNull,
    Or,
)

Style = Literal["bind", "literal"]


def _quote_ident(name: str) -> str:
    return f'"{name}"'


def _literal_sql(value: str | int | float) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + value.replace("'", "''") + "'"


def render_sql_condition(
    expr: ConditionExpr,
    style: Style,
) -> tuple[str, dict[str, Any]]:
    """Return ``(fragment, params)``; params is empty for literal style."""
    params: dict[str, Any] = {}

    def _value(value: str | int | float) -> str:
        if style == "literal":
            return _literal_sql(value)
        key = f"cond_{len(params)}"
        params[key] = value
        return f"%({key})s"

    def _render(e: ConditionExpr) -> str:
        if isinstance(e, Comparison):
            return f"{_quote_ident(e.column)} {e.op} {_value(e.literal)}"
        if isinstance(e, IsNull):
            suffix = "IS NOT NULL" if e.negated else "IS NULL"
            return f"{_quote_ident(e.column)} {suffix}"
        if isinstance(e, InList):
            rendered = ", ".join(_value(v) for v in e.values)
            keyword = "NOT IN" if e.negated else "IN"
            return f"{_quote_ident(e.column)} {keyword} ({rendered})"
        if isinstance(e, And):
            return "(" + " AND ".join(_render(i) for i in e.items) + ")"
        if isinstance(e, Or):
            return "(" + " OR ".join(_render(i) for i in e.items) + ")"
        raise TypeError(f"unknown condition node {type(e).__name__}")

    return _render(expr), params
