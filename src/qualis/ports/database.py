from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator


class DatabasePort(Protocol):
    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> int: ...

    def stream(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        chunk_size: int = 10_000,
    ) -> Iterator[list[dict[str, Any]]]: ...

    def table_exists(self, schema: str, table: str) -> bool: ...

    def check_not_null(self, schema: str, table: str, column: str) -> dict[str, int]: ...

    def check_unique(self, schema: str, table: str, column: str) -> dict[str, int]: ...

    def check_between(
        self,
        schema: str,
        table: str,
        column: str,
        min_val: str,
        max_val: str,
    ) -> dict[str, int]: ...

    def check_regex(
        self,
        schema: str,
        table: str,
        column: str,
        pattern: str,
    ) -> dict[str, int]: ...
