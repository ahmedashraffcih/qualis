from __future__ import annotations

import dataclasses

import pytest

from qualis.domain.context import (
    ColumnContext,
    DatasetContext,
    SentinelDeclaration,
)


class TestSentinelDeclaration:
    def test_construction(self) -> None:
        s = SentinelDeclaration(value="0", meaning="unknown")
        assert s.value == "0"
        assert s.meaning == "unknown"

    def test_frozen(self) -> None:
        s = SentinelDeclaration(value="0", meaning="unknown")
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.value = "1"  # type: ignore[misc]


class TestColumnContext:
    def test_minimal_construction(self) -> None:
        c = ColumnContext(column="code")
        assert c.column == "code"
        assert c.sentinels == []
        assert c.exceptions == []
        assert c.notes == ""

    def test_with_sentinels(self) -> None:
        c = ColumnContext(
            column="code",
            sentinels=[SentinelDeclaration(value="0", meaning="unknown")],
        )
        assert len(c.sentinels) == 1
        assert c.sentinels[0].value == "0"

    def test_with_exceptions(self) -> None:
        c = ColumnContext(column="severity_code", exceptions=["LEGACY_CODE_X"])
        assert c.exceptions == ["LEGACY_CODE_X"]


class TestDatasetContext:
    def test_minimal_construction(self) -> None:
        d = DatasetContext(dataset="accidents")
        assert d.dataset == "accidents"
        assert d.columns == {}
        assert d.business_grain is None

    def test_with_columns(self) -> None:
        d = DatasetContext(
            dataset="accidents",
            columns={
                "code": ColumnContext(
                    column="code",
                    sentinels=[SentinelDeclaration(value="0", meaning="unknown")],
                ),
            },
        )
        assert "code" in d.columns
        assert d.columns["code"].sentinels[0].value == "0"

    def test_with_business_grain(self) -> None:
        d = DatasetContext(
            dataset="accidents",
            business_grain="one row per accident, deduplicated by (accident_id, report_date)",
        )
        assert d.business_grain is not None
        assert "accident_id" in d.business_grain

    def test_get_column_returns_empty_default(self) -> None:
        d = DatasetContext(dataset="accidents")
        ctx = d.get_column("unconfigured_col")
        assert isinstance(ctx, ColumnContext)
        assert ctx.column == "unconfigured_col"
        assert ctx.sentinels == []

    def test_get_column_returns_configured(self) -> None:
        d = DatasetContext(
            dataset="accidents",
            columns={
                "code": ColumnContext(
                    column="code",
                    sentinels=[SentinelDeclaration(value="0", meaning="unknown")],
                ),
            },
        )
        ctx = d.get_column("code")
        assert ctx.sentinels[0].value == "0"
