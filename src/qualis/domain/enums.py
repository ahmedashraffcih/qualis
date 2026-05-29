from __future__ import annotations

from enum import StrEnum


class DQDimension(StrEnum):
    """DAMA DMBOK 2.0 -- all 9 canonical data quality dimensions."""

    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CONSISTENCY = "consistency"
    VALIDITY = "validity"
    UNIQUENESS = "uniqueness"
    TIMELINESS = "timeliness"
    REASONABILITY = "reasonability"
    INTEGRITY = "integrity"
    CURRENCY = "currency"


class RuleType(StrEnum):
    ROW_LEVEL = "row_level"
    AGGREGATE = "aggregate"
    REFERENTIAL = "referential"
    COMPOSITE = "composite"


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class CheckType(StrEnum):
    NOT_NULL = "not_null"
    UNIQUE = "unique"
    BETWEEN = "between"
    REGEX = "regex"
    SQL = "sql"
    CUSTOM = "custom"
    IN_SET = "in_set"
    ROW_COUNT = "row_count"
    NOT_NEGATIVE = "not_negative"
