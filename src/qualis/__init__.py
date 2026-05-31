"""Qualis — Data quality framework that tells you WHAT failed."""

from __future__ import annotations

__version__ = "0.2.2"

from qualis.domain.enums import DQDimension, RunStatus, Severity
from qualis.domain.models import DatasetScore, Rule, Violation
from qualis.ports.database import DatabasePort
from qualis.ports.notifier import NotifierPort

__all__ = [
    "DQDimension",
    "DatabasePort",
    "DatasetScore",
    "NotifierPort",
    "Rule",
    "RunStatus",
    "Severity",
    "Violation",
    "__version__",
]
