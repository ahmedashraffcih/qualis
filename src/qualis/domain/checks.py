from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from qualis.domain.models import Violation


class RowLevelCheck(Protocol):
    def evaluate(self, row: dict[str, Any]) -> Violation | None: ...
