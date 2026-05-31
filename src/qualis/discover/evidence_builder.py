"""Build SuggestionEvidence from a ColumnProfile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualis.domain.evidence import ProfileEvidence

if TYPE_CHECKING:
    from qualis.discover.profiler import ColumnProfile


def build_profile_evidence(
    col: ColumnProfile,
    top_values: list[tuple[str, int]],
) -> ProfileEvidence:
    """Snapshot the column profile into immutable evidence.

    ``top_values`` is passed in (not pulled from ``col``) because the
    profiler does not currently compute it; callers that have it
    available include it, callers that don't pass an empty list.
    """
    return ProfileEvidence(
        total_rows=col.total_count,
        null_count=col.null_count,
        null_fraction=col.null_fraction,
        distinct_count=col.distinct_count,
        distinct_fraction=col.distinct_fraction,
        min_value=col.min_value,
        max_value=col.max_value,
        top_values=top_values,
    )
