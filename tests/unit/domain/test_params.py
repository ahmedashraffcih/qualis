from __future__ import annotations

import dataclasses

import pytest

from qualis.domain.params import (
    BetweenParams,
    CheckParams,
    CustomParams,
    InSetParams,
    NotNegativeParams,
    NotNullParams,
    RegexParams,
    RowCountParams,
    SqlParams,
    UniqueParams,
)


class TestNotNullParams:
    def test_construction(self) -> None:
        p = NotNullParams()
        assert isinstance(p, NotNullParams)

    def test_is_frozen(self) -> None:
        p = NotNullParams()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            p.anything = "value"  # type: ignore[attr-defined]

    def test_equality(self) -> None:
        assert NotNullParams() == NotNullParams()

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(NotNullParams)


class TestUniqueParams:
    def test_construction(self) -> None:
        p = UniqueParams()
        assert isinstance(p, UniqueParams)

    def test_is_frozen(self) -> None:
        p = UniqueParams()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            p.anything = "value"  # type: ignore[attr-defined]

    def test_equality(self) -> None:
        assert UniqueParams() == UniqueParams()

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(UniqueParams)


class TestBetweenParams:
    def test_construction(self) -> None:
        p = BetweenParams(min="0", max="100")
        assert p.min == "0"
        assert p.max == "100"

    def test_min_value(self) -> None:
        p = BetweenParams(min="10", max="200")
        assert p.min == "10"

    def test_max_value(self) -> None:
        p = BetweenParams(min="10", max="200")
        assert p.max == "200"

    def test_is_frozen(self) -> None:
        p = BetweenParams(min="0", max="100")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            p.min = "999"  # type: ignore[misc]

    def test_immutable_max(self) -> None:
        p = BetweenParams(min="0", max="100")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            p.max = "999"  # type: ignore[misc]

    def test_equality(self) -> None:
        assert BetweenParams(min="0", max="100") == BetweenParams(min="0", max="100")

    def test_inequality(self) -> None:
        assert BetweenParams(min="0", max="100") != BetweenParams(min="1", max="100")

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(BetweenParams)

    def test_negative_bounds(self) -> None:
        p = BetweenParams(min="-100", max="-1")
        assert p.min == "-100"
        assert p.max == "-1"

    def test_string_fields_preserved(self) -> None:
        # min/max are str to support decimal, date, or numeric ranges in YAML
        p = BetweenParams(min="2024-01-01", max="2024-12-31")
        assert p.min == "2024-01-01"
        assert p.max == "2024-12-31"


class TestRegexParams:
    def test_construction(self) -> None:
        p = RegexParams(pattern=r"^\d{4}$")
        assert p.pattern == r"^\d{4}$"

    def test_pattern_value(self) -> None:
        p = RegexParams(pattern=r"^[a-z]+$")
        assert p.pattern == r"^[a-z]+$"

    def test_is_frozen(self) -> None:
        p = RegexParams(pattern=r"\d+")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            p.pattern = "new_pattern"  # type: ignore[misc]

    def test_equality(self) -> None:
        assert RegexParams(pattern=r"\d+") == RegexParams(pattern=r"\d+")

    def test_inequality(self) -> None:
        assert RegexParams(pattern=r"\d+") != RegexParams(pattern=r"\w+")

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(RegexParams)

    def test_complex_pattern(self) -> None:
        pattern = r"^(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}$"
        p = RegexParams(pattern=pattern)
        assert p.pattern == pattern


class TestSqlParams:
    def test_construction(self) -> None:
        p = SqlParams(expression="value > 0")
        assert p.expression == "value > 0"

    def test_expression_value(self) -> None:
        p = SqlParams(expression="col IS NOT NULL AND col > 0")
        assert p.expression == "col IS NOT NULL AND col > 0"

    def test_is_frozen(self) -> None:
        p = SqlParams(expression="value > 0")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            p.expression = "value < 0"  # type: ignore[misc]

    def test_equality(self) -> None:
        assert SqlParams(expression="x > 0") == SqlParams(expression="x > 0")

    def test_inequality(self) -> None:
        assert SqlParams(expression="x > 0") != SqlParams(expression="x < 0")

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(SqlParams)

    def test_multiline_expression(self) -> None:
        expr = "col_a > 0\nAND col_b IS NOT NULL"
        p = SqlParams(expression=expr)
        assert p.expression == expr


class TestCustomParams:
    def test_construction(self) -> None:
        p = CustomParams(handler="mymodule.validators.check_email")
        assert p.handler == "mymodule.validators.check_email"

    def test_handler_value(self) -> None:
        p = CustomParams(handler="pkg.module:function")
        assert p.handler == "pkg.module:function"

    def test_is_frozen(self) -> None:
        p = CustomParams(handler="my.handler")
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            p.handler = "other.handler"  # type: ignore[misc]

    def test_equality(self) -> None:
        assert CustomParams(handler="a.b.c") == CustomParams(handler="a.b.c")

    def test_inequality(self) -> None:
        assert CustomParams(handler="a.b") != CustomParams(handler="a.c")

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(CustomParams)


class TestCheckParamsUnion:
    def test_not_null_is_check_params(self) -> None:
        p: CheckParams = NotNullParams()
        assert isinstance(p, NotNullParams)

    def test_unique_is_check_params(self) -> None:
        p: CheckParams = UniqueParams()
        assert isinstance(p, UniqueParams)

    def test_between_is_check_params(self) -> None:
        p: CheckParams = BetweenParams(min="0", max="10")
        assert isinstance(p, BetweenParams)

    def test_regex_is_check_params(self) -> None:
        p: CheckParams = RegexParams(pattern=r"\d+")
        assert isinstance(p, RegexParams)

    def test_sql_is_check_params(self) -> None:
        p: CheckParams = SqlParams(expression="value > 0")
        assert isinstance(p, SqlParams)

    def test_custom_is_check_params(self) -> None:
        p: CheckParams = CustomParams(handler="my.handler")
        assert isinstance(p, CustomParams)

    def test_union_covers_all_nine_types(self) -> None:
        # All nine param types can be assigned to a CheckParams annotated variable
        params: list[CheckParams] = [
            NotNullParams(),
            UniqueParams(),
            BetweenParams(min="0", max="100"),
            RegexParams(pattern=r"\w+"),
            SqlParams(expression="col > 0"),
            CustomParams(handler="mod.fn"),
            InSetParams(values=["A", "B"]),
            RowCountParams(min=1, max=100),
            NotNegativeParams(),
        ]
        assert len(params) == 9


class TestInSetParams:
    def test_construction(self) -> None:
        p = InSetParams(values=["A", "B", "C"])
        assert p.values == ["A", "B", "C"]

    def test_frozen(self) -> None:
        p = InSetParams(values=["A"])
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.values = ["B"]  # type: ignore[misc]


class TestRowCountParams:
    def test_construction_with_both_bounds(self) -> None:
        p = RowCountParams(min=10, max=100)
        assert p.min == 10
        assert p.max == 100

    def test_defaults_are_none(self) -> None:
        p = RowCountParams()
        assert p.min is None
        assert p.max is None

    def test_min_only(self) -> None:
        p = RowCountParams(min=5)
        assert p.min == 5
        assert p.max is None


class TestNotNegativeParams:
    def test_construction(self) -> None:
        p = NotNegativeParams()
        assert isinstance(p, NotNegativeParams)

    def test_frozen(self) -> None:
        p = NotNegativeParams()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.x = 1  # type: ignore[attr-defined]


def test_reference_lookup_params_construction() -> None:
    from qualis.domain.params import ReferenceLookupParams
    p = ReferenceLookupParams(reference="ref_codes", key_column="code")
    assert p.reference == "ref_codes"
    assert p.key_column == "code"


def test_reference_lookup_params_is_check_params() -> None:
    from qualis.domain.params import ReferenceLookupParams
    p: CheckParams = ReferenceLookupParams(reference="x", key_column="y")
    assert isinstance(p, ReferenceLookupParams)
