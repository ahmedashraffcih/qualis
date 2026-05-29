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
)
