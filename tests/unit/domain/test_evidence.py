from __future__ import annotations

import dataclasses

import pytest

from qualis.domain.evidence import ProfileEvidence, SuggestionEvidence


class TestProfileEvidence:
    def test_construction(self) -> None:
        e = ProfileEvidence(
            total_rows=1000, null_count=0, null_fraction=0.0,
            distinct_count=4, distinct_fraction=0.004,
            min_value="FATAL", max_value="SERIOUS",
            top_values=[("MINOR", 700), ("SERIOUS", 200), ("FATAL", 80), ("PROPERTY", 20)],
        )
        assert e.total_rows == 1000
        assert e.distinct_count == 4
        assert e.top_values[0] == ("MINOR", 700)

    def test_frozen(self) -> None:
        e = ProfileEvidence(
            total_rows=1, null_count=0, null_fraction=0.0,
            distinct_count=1, distinct_fraction=1.0,
            min_value=None, max_value=None, top_values=[],
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.total_rows = 2  # type: ignore[misc]


class TestSuggestionEvidence:
    def test_construction_with_profile_only(self) -> None:
        profile = ProfileEvidence(
            total_rows=100, null_count=0, null_fraction=0.0,
            distinct_count=4, distinct_fraction=0.04,
            min_value=None, max_value=None, top_values=[],
        )
        e = SuggestionEvidence(
            profile=profile, heuristic="not_null",
            heuristic_reason="0 nulls observed in 100 rows",
        )
        assert e.profile.total_rows == 100
        assert e.heuristic == "not_null"
        assert e.sentinels_consulted == []
        assert e.exceptions_consulted == []
        assert e.estimated_violation_rate is None

    def test_construction_with_estimated_violation_rate(self) -> None:
        profile = ProfileEvidence(
            total_rows=100, null_count=5, null_fraction=0.05,
            distinct_count=4, distinct_fraction=0.04,
            min_value=None, max_value=None, top_values=[],
        )
        e = SuggestionEvidence(
            profile=profile, heuristic="not_null",
            heuristic_reason="5 nulls in 100 rows", estimated_violation_rate=0.05,
        )
        assert e.estimated_violation_rate == 0.05

    def test_construction_with_consulted_sentinels(self) -> None:
        profile = ProfileEvidence(
            total_rows=100, null_count=0, null_fraction=0.0,
            distinct_count=4, distinct_fraction=0.04,
            min_value=None, max_value=None, top_values=[],
        )
        e = SuggestionEvidence(
            profile=profile, heuristic="in_set",
            heuristic_reason="4 distinct values", sentinels_consulted=["0"],
        )
        assert e.sentinels_consulted == ["0"]
