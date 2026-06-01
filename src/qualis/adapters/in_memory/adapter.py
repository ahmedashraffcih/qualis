from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator


class InMemoryAdapter:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}

    def add_table(self, schema: str, table: str, rows: list[dict[str, Any]]) -> None:
        self._tables[f"{schema}.{table}"] = list(rows)

    def _get_rows(self, schema: str, table: str) -> list[dict[str, Any]]:
        key = f"{schema}.{table}"
        if key not in self._tables:
            raise ValueError(f"Table {key} not found")
        return self._tables[key]

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        table_key = self._extract_table_from_sql(sql)
        if table_key and table_key in self._tables:
            return list(self._tables[table_key])
        return []

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        return 0

    def stream(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
        chunk_size: int = 10_000,
    ) -> Iterator[list[dict[str, Any]]]:
        table_key = self._extract_table_from_sql(sql)
        if table_key and table_key in self._tables:
            rows = self._tables[table_key]
            for i in range(0, len(rows), chunk_size):
                yield rows[i : i + chunk_size]

    def table_exists(self, schema: str, table: str) -> bool:
        return f"{schema}.{table}" in self._tables

    def check_not_null(self, schema: str, table: str, column: str) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        null_count = sum(1 for r in rows if r.get(column) is None)
        return {"null_count": null_count, "total_count": len(rows)}

    def check_unique(self, schema: str, table: str, column: str) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        values = [r.get(column) for r in rows if r.get(column) is not None]
        duplicate_count = len(values) - len(set(values))
        return {"duplicate_count": duplicate_count, "total_count": len(rows)}

    def check_between(
        self,
        schema: str,
        table: str,
        column: str,
        min_val: str,
        max_val: str,
    ) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        out_count = 0
        checked = 0
        for r in rows:
            val = r.get(column)
            if val is None:
                continue
            checked += 1
            if str(val) < min_val or str(val) > max_val:
                out_count += 1
        return {"out_of_range_count": out_count, "total_count": len(rows), "checked": checked}

    def check_regex(
        self,
        schema: str,
        table: str,
        column: str,
        pattern: str,
    ) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        compiled = re.compile(pattern)
        non_matching = sum(
            1
            for r in rows
            if r.get(column) is None or not compiled.match(str(r.get(column)))
        )
        return {"non_matching_count": non_matching, "total_count": len(rows)}

    def check_in_set(
        self,
        schema: str,
        table: str,
        column: str,
        values: list[str],
    ) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        allowed = set(values)
        invalid_count = sum(
            1
            for r in rows
            if r.get(column) is None or str(r.get(column)) not in allowed
        )
        return {"invalid_count": invalid_count, "total_count": len(rows)}

    def check_row_count(self, schema: str, table: str) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        return {"row_count": len(rows)}

    def check_not_negative(
        self,
        schema: str,
        table: str,
        column: str,
    ) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        negative_count = sum(
            1
            for r in rows
            if r.get(column) is not None and (r[column]) < 0
        )
        return {"negative_count": negative_count, "total_count": len(rows)}

    def check_reference_lookup(
        self,
        schema: str,
        table: str,
        column: str,
        valid_values: list[str],
    ) -> dict[str, int]:
        rows = self._get_rows(schema, table)
        valid_set = set(valid_values)
        invalid_count = sum(
            1
            for r in rows
            if r.get(column) is not None and r.get(column) not in valid_set
        )
        return {"invalid_count": invalid_count, "total_count": len(rows)}

    def _extract_table_from_sql(self, sql: str) -> str | None:
        match = re.search(r"FROM\s+(\S+)", sql, re.IGNORECASE)
        return match.group(1) if match else None
