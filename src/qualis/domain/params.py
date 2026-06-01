from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotNullParams:
    pass


@dataclass(frozen=True)
class UniqueParams:
    pass


@dataclass(frozen=True)
class BetweenParams:
    min: str
    max: str


@dataclass(frozen=True)
class RegexParams:
    pattern: str


@dataclass(frozen=True)
class SqlParams:
    expression: str


@dataclass(frozen=True)
class CustomParams:
    handler: str


@dataclass(frozen=True)
class InSetParams:
    values: list[str]


@dataclass(frozen=True)
class RowCountParams:
    min: int | None = None
    max: int | None = None


@dataclass(frozen=True)
class NotNegativeParams:
    pass


@dataclass(frozen=True)
class ReferenceLookupParams:
    """Parameters for reference_lookup check.

    ``reference`` is an identifier the ReferenceDataPort resolves (file
    path, table name, or registered logical name -- adapter-dependent).
    ``key_column`` is the column in the reference whose values the
    rule's target column must match.
    """

    reference: str
    key_column: str


CheckParams = (
    NotNullParams
    | UniqueParams
    | BetweenParams
    | RegexParams
    | SqlParams
    | CustomParams
    | InSetParams
    | RowCountParams
    | NotNegativeParams
    | ReferenceLookupParams  # new in v0.3.0
)
