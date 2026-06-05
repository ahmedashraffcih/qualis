"""Constrained condition grammar — the trust boundary for ``Rule.condition``.

Conditions are untrusted text wherever they come from (rule YAML, dbt
``meta`` blocks, LLM-suggested rules). This parser is the allowlist: only
the constructs below exist past it, so adapter renderers can emit SQL from
the AST without ever interpolating user text as syntax. See AgDR-0005.

Grammar v1::

    condition  := or_expr
    or_expr    := and_expr (OR and_expr)*
    and_expr   := unary (AND unary)*
    unary      := '(' or_expr ')' | predicate
    predicate  := column op literal
                | column IS [NOT] NULL
                | column [NOT] IN '(' literal (',' literal)* ')'
    op         := = | != | <> | < | <= | > | >=
    column     := bare identifier  (letters, digits, underscore)
    literal    := single-quoted string | [-]integer | [-]decimal
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(
    r"""
    \s*(
        '(?:[^']|'')*'           # string literal ('' = escaped quote)
      | -?\d+(?:\.\d+)?          # signed number (review condition C1)
      | [A-Za-z_][A-Za-z0-9_]*   # identifier / keyword
      | <> | != | <= | >= | [=<>(),]
    )
    """,
    re.VERBOSE,
)

_KEYWORDS = {"AND", "OR", "IS", "NOT", "NULL", "IN"}
_OPS = {"=", "!=", "<>", "<", "<=", ">", ">="}


class ConditionError(ValueError):
    """A condition failed to parse or evaluate — always carries context."""


@dataclass(frozen=True)
class Comparison:
    column: str
    op: str
    literal: str | int | float

    def columns(self) -> set[str]:
        return {self.column}


@dataclass(frozen=True)
class IsNull:
    column: str
    negated: bool

    def columns(self) -> set[str]:
        return {self.column}


@dataclass(frozen=True)
class InList:
    column: str
    values: tuple[str | int | float, ...]
    negated: bool

    def columns(self) -> set[str]:
        return {self.column}


@dataclass(frozen=True)
class And:
    items: tuple[ConditionExpr, ...]

    def columns(self) -> set[str]:
        return set().union(*(i.columns() for i in self.items))


@dataclass(frozen=True)
class Or:
    items: tuple[ConditionExpr, ...]

    def columns(self) -> set[str]:
        return set().union(*(i.columns() for i in self.items))


ConditionExpr = Comparison | IsNull | InList | And | Or


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise ConditionError(
                f"invalid token at position {pos}: {text[pos:pos + 20]!r}"
            )
        token = match.group(1)
        tokens.append(token)
        pos = match.end()
    # trailing whitespace-only remainder is fine; anything else was caught
    return tokens


class _Parser:
    def __init__(self, tokens: list[str], source: str) -> None:
        self._tokens = tokens
        self._source = source
        self._pos = 0

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> str:
        token = self._peek()
        if token is None:
            raise ConditionError(f"unexpected end of condition: {self._source!r}")
        self._pos += 1
        return token

    def _keyword(self, token: str | None) -> str | None:
        if token is not None and token.upper() in _KEYWORDS:
            return token.upper()
        return None

    def parse(self) -> ConditionExpr:
        expr = self._or_expr()
        if self._peek() is not None:
            raise ConditionError(
                f"unexpected trailing input {self._peek()!r} in {self._source!r}"
            )
        return expr

    def _or_expr(self) -> ConditionExpr:
        items = [self._and_expr()]
        while self._keyword(self._peek()) == "OR":
            self._next()
            items.append(self._and_expr())
        return items[0] if len(items) == 1 else Or(tuple(items))

    def _and_expr(self) -> ConditionExpr:
        items = [self._unary()]
        while self._keyword(self._peek()) == "AND":
            self._next()
            items.append(self._unary())
        return items[0] if len(items) == 1 else And(tuple(items))

    def _unary(self) -> ConditionExpr:
        if self._peek() == "(":
            self._next()
            expr = self._or_expr()
            if self._next() != ")":
                raise ConditionError(f"expected ')' in {self._source!r}")
            return expr
        return self._predicate()

    def _identifier(self) -> str:
        token = self._next()
        if self._keyword(token) is not None or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", token
        ):
            raise ConditionError(
                f"expected a column name, got {token!r} in {self._source!r}"
            )
        return token

    def _literal(self) -> str | int | float:
        token = self._next()
        if token.startswith("'") and token.endswith("'") and len(token) >= 2:
            return token[1:-1].replace("''", "'")
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        if re.fullmatch(r"-?\d+\.\d+", token):
            return float(token)
        raise ConditionError(
            f"expected a literal (quoted string or number), got {token!r} "
            f"in {self._source!r}"
        )

    def _predicate(self) -> ConditionExpr:
        column = self._identifier()
        token = self._next()
        keyword = self._keyword(token)

        if keyword == "IS":
            negated = False
            token = self._next()
            if self._keyword(token) == "NOT":
                negated = True
                token = self._next()
            if self._keyword(token) != "NULL":
                raise ConditionError(f"expected NULL after IS in {self._source!r}")
            return IsNull(column, negated)

        negated = False
        if keyword == "NOT":
            negated = True
            token = self._next()
            keyword = self._keyword(token)
        if keyword == "IN":
            if self._next() != "(":
                raise ConditionError(f"expected '(' after IN in {self._source!r}")
            values: list[str | int | float] = []
            if self._peek() == ")":
                raise ConditionError(
                    f"IN () with no values is always false — author error "
                    f"in {self._source!r}"
                )
            values.append(self._literal())
            while self._peek() == ",":
                self._next()
                values.append(self._literal())
            if self._next() != ")":
                raise ConditionError(f"expected ')' closing IN in {self._source!r}")
            return InList(column, tuple(values), negated)

        if token in _OPS:
            return Comparison(column, "!=" if token == "<>" else token, self._literal())

        raise ConditionError(
            f"expected an operator, IS or IN after {column!r}, got {token!r} "
            f"in {self._source!r}"
        )


def parse_condition(text: str) -> ConditionExpr:
    """Parse *text* against grammar v1 or raise :class:`ConditionError`."""
    if not text or not text.strip():
        raise ConditionError("condition is empty")
    return _Parser(_tokenize(text), text).parse()


# ---------------------------------------------------------------------------
# Python evaluation (used by the in-memory adapter)
# ---------------------------------------------------------------------------


def _compare(value: Any, op: str, literal: str | int | float) -> bool:
    if value is None:
        return False  # SQL three-valued logic collapses to not-matching
    coerced: Any = value
    if isinstance(literal, (int, float)):
        try:
            coerced = float(value)
        except (TypeError, ValueError):
            return False
        literal = float(literal)
    else:
        coerced = str(value)
    if op == "=":
        return bool(coerced == literal)
    if op == "!=":
        return bool(coerced != literal)
    if op == "<":
        return bool(coerced < literal)
    if op == "<=":
        return bool(coerced <= literal)
    if op == ">":
        return bool(coerced > literal)
    if op == ">=":
        return bool(coerced >= literal)
    raise ConditionError(f"unknown operator {op!r}")  # pragma: no cover


def evaluate_condition(expr: ConditionExpr, row: dict[str, Any]) -> bool:
    """Evaluate *expr* against a row dict with SQL-like NULL semantics.

    A condition naming a column absent from the row raises a located
    :class:`ConditionError` (review condition C3) — distinct from a column
    that is present with a NULL value.
    """
    for name in expr.columns():
        if name not in row:
            raise ConditionError(f"condition references unknown column {name!r}")

    def _eval(e: ConditionExpr) -> bool:
        if isinstance(e, Comparison):
            return _compare(row.get(e.column), e.op, e.literal)
        if isinstance(e, IsNull):
            is_null = row.get(e.column) is None
            return (not is_null) if e.negated else is_null
        if isinstance(e, InList):
            value = row.get(e.column)
            if value is None:
                return False
            matched = any(_compare(value, "=", v) for v in e.values)
            return (not matched) if e.negated else matched
        if isinstance(e, And):
            return all(_eval(i) for i in e.items)
        if isinstance(e, Or):
            return any(_eval(i) for i in e.items)
        raise ConditionError(f"unknown node {type(e).__name__}")  # pragma: no cover

    return _eval(expr)
