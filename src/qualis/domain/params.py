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

    ``reference_schema`` (optional) declares that the reference is a TABLE
    co-located in the checked database at ``reference_schema.reference``.
    Setting it opts in to JOIN pushdown; the adapter's ``table_exists``
    probe must confirm before the JOIN path runs (AgDR-0006 — detected,
    never assumed). Unset = the classic ReferenceDataPort values path.
    """

    reference: str
    key_column: str
    reference_schema: str | None = None


@dataclass(frozen=True)
class CrossDatasetParams:
    """Parameters for cross_dataset_assertion (AgDR-0008).

    Compares one aggregate between the rule's dataset and
    ``reference_dataset`` (``table`` or ``schema.table``, same database).

    ``metric`` is whitelisted at load time — v1 ships ``row_count`` and
    ``sum`` only (``count_distinct`` deliberately deferred: hash-aggregate
    spill at high cardinality). For ``sum`` the target column is the
    rule's own ``column``; ``reference_column`` defaults to it.

    ``tolerance_pct`` is kept as the YAML string and parsed as a
    non-negative ``Decimal`` percentage — float would lose precision
    against ``numeric`` sums.
    """

    metric: str
    reference_dataset: str
    reference_column: str | None = None
    tolerance_pct: str = "0"


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
    | CrossDatasetParams  # new in v0.6.0
)
