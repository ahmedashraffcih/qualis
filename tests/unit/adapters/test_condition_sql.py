from __future__ import annotations

from qualis.adapters._condition_sql import render_sql_condition
from qualis.domain.condition import parse_condition


class TestLiteralStyle:
    def test_string_escaping_doubles_quotes(self) -> None:
        frag, params = render_sql_condition(
            parse_condition("name = 'O''Brien'"), "literal"
        )
        assert frag == "\"name\" = 'O''Brien'"
        assert params == {}

    def test_identifiers_double_quoted(self) -> None:
        frag, _ = render_sql_condition(parse_condition("order > 5"), "literal")
        assert frag == '"order" > 5'

    def test_combinators_parenthesised(self) -> None:
        frag, _ = render_sql_condition(
            parse_condition("(a = 1 OR b = 2) AND c IS NULL"), "literal"
        )
        assert frag == '(("a" = 1 OR "b" = 2) AND "c" IS NULL)'


class TestBindStyle:
    def test_values_become_named_binds(self) -> None:
        frag, params = render_sql_condition(
            parse_condition("status = 'active' AND amount > -10"), "bind"
        )
        assert frag == '("status" = %(cond_0)s AND "amount" > %(cond_1)s)'
        assert params == {"cond_0": "active", "cond_1": -10}

    def test_in_list_binds_each_value(self) -> None:
        frag, params = render_sql_condition(
            parse_condition("sev NOT IN ('A', 'B')"), "bind"
        )
        assert frag == '"sev" NOT IN (%(cond_0)s, %(cond_1)s)'
        assert params == {"cond_0": "A", "cond_1": "B"}
