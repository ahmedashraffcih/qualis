from __future__ import annotations

import dataclasses

import pytest

from qualis.domain.standards import RuleMetadataSchema, StandardField


class TestStandardField:
    def test_minimal_required_field(self) -> None:
        f = StandardField(name="owner", required=True)
        assert f.name == "owner"
        assert f.required is True
        assert f.description == ""
        assert f.allowed_values is None

    def test_optional_field_with_enum(self) -> None:
        f = StandardField(
            name="frequency", required=False,
            description="how often the rule runs",
            allowed_values=["hourly", "daily", "weekly", "monthly"],
        )
        assert f.required is False
        assert f.allowed_values == ["hourly", "daily", "weekly", "monthly"]

    def test_frozen(self) -> None:
        f = StandardField(name="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.name = "y"  # type: ignore[misc]


class TestRuleMetadataSchema:
    def test_empty_schema(self) -> None:
        s = RuleMetadataSchema()
        assert s.fields == []

    def test_schema_with_required_fields(self) -> None:
        s = RuleMetadataSchema(
            fields=[
                StandardField(name="owner", required=True),
                StandardField(name="cde", required=True),
                StandardField(name="glossary_term", required=False),
            ],
        )
        assert len(s.fields) == 3
        required = [f for f in s.fields if f.required]
        assert len(required) == 2

    def test_get_field_by_name(self) -> None:
        s = RuleMetadataSchema(
            fields=[
                StandardField(name="owner", required=True),
                StandardField(name="cde", required=True),
            ],
        )
        owner = s.get_field("owner")
        assert owner is not None
        assert owner.required is True
        assert s.get_field("nonexistent") is None
