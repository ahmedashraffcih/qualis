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


CheckParams = NotNullParams | UniqueParams | BetweenParams | RegexParams | SqlParams | CustomParams
