"""Domain context that the data cannot tell you.

The practitioner critique: a value of 0 might be a valid sentinel
("unknown") in some tables and an invalid entry in others. The data
itself cannot resolve this. The suggester must consult declared context
before generating rules, otherwise it codifies the sentinel as valid
data at "high" confidence and ships the failure mode at scale.

This module holds the user-correctable context as immutable data.
The suggester consumes it; the loader populates it from context.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SentinelDeclaration:
    """A value that appears in the data but has a special meaning the
    suggester should respect.

    Example: ``SentinelDeclaration(value="0", meaning="unknown")``
    tells the suggester that 0 is a legitimate placeholder, not a
    real domain value. The suggester should EXCLUDE this value when
    proposing ``in_set`` or ``between`` rules.
    """

    value: str
    meaning: str


@dataclass(frozen=True)
class ColumnContext:
    """Per-column context the suggester should consult.

    sentinels  -- values the suggester should exclude from observed-value rule generation
    exceptions -- known-valid values that may not appear in the profile sample
    notes      -- free-text reviewer note (shown in review screen, not consumed by suggester)
    """

    column: str
    sentinels: list[SentinelDeclaration] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class DatasetContext:
    """Dataset-level context: per-column annotations + business grain.

    business_grain -- the join key the business actually counts at
    (free-text; suggester does not consume this in v0.3.0, but the
    review screen surfaces it so reviewers can spot wrong-key joins).
    """

    dataset: str
    columns: dict[str, ColumnContext] = field(default_factory=dict)
    business_grain: str | None = None

    def get_column(self, column: str) -> ColumnContext:
        """Return the ColumnContext for *column*, or an empty one if absent.

        Empty context (not None) keeps suggester code branch-free.
        """
        if column in self.columns:
            return self.columns[column]
        return ColumnContext(column=column)


EMPTY_CONTEXT = DatasetContext(dataset="")
"""Sentinel: a context with no annotations. Default when caller has none."""
