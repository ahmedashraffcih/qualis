from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from qualis.domain.condition import evaluate_condition

if TYPE_CHECKING:
    from collections.abc import Iterator

    from qualis.domain.condition import ConditionExpr


class InMemoryAdapter:
    #: Conditioned rules are honoured (AgDR-0005) — the engine checks this
    #: flag and skips conditioned rules on adapters that lack it.
    supports_conditions = True

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}

    def add_table(self, schema: str, table: str, rows: list[dict[str, Any]]) -> None:
        self._tables[f"{schema}.{table}"] = list(rows)

    def _get_rows(self, schema: str, table: str) -> list[dict[str, Any]]:
        key = f"{schema}.{table}"
        if key not in self._tables:
            raise ValueError(f"Table {key} not found")
        return self._tables[key]

    def _population(
        self,
        schema: str,
        table: str,
        condition: ConditionExpr | None,
    ) -> list[dict[str, Any]]:
        rows = self._get_rows(schema, table)
        if condition is None:
            return rows
        return [r for r in rows if evaluate_condition(condition, r)]

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

    def check_not_null(
        self,
        schema: str,
        table: str,
        column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
        null_count = sum(1 for r in rows if r.get(column) is None)
        return {"null_count": null_count, "total_count": len(rows)}

    def check_unique(
        self,
        schema: str,
        table: str,
        column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
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
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
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
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
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
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
        allowed = set(values)
        invalid_count = sum(
            1
            for r in rows
            if r.get(column) is None or str(r.get(column)) not in allowed
        )
        return {"invalid_count": invalid_count, "total_count": len(rows)}

    def check_row_count(
        self,
        schema: str,
        table: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
        return {"row_count": len(rows)}

    def check_not_negative(
        self,
        schema: str,
        table: str,
        column: str,
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
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
        condition: ConditionExpr | None = None,
    ) -> dict[str, int]:
        rows = self._population(schema, table, condition)
        valid_set = set(valid_values)
        invalid_count = sum(
            1
            for r in rows
            if r.get(column) is not None and r.get(column) not in valid_set
        )
        return {"invalid_count": invalid_count, "total_count": len(rows)}

    def fetch_violation_samples(
        self,
        schema: str,
        table: str,
        column: str,
        kind: str,
        params: dict[str, Any],
        limit: int,
        condition: ConditionExpr | None = None,
    ) -> list[dict[str, Any]]:
        """Optional capability: return up to *limit* failing rows as evidence.

        Each predicate mirrors the corresponding ``check_*`` count semantics
        exactly, so sampled rows are always members of the counted set.
        ``record_id`` is the zero-based row index in the table.
        """
        rows = self._population(schema, table, condition)

        def fails(value: Any) -> bool:
            if kind == "not_null":
                return value is None
            if kind == "unique":
                if value is None:
                    return False
                non_null = [r.get(column) for r in rows if r.get(column) is not None]
                return non_null.count(value) > 1
            if kind == "between":
                return value is not None and (
                    str(value) < params["min"] or str(value) > params["max"]
                )
            if kind == "regex":
                return value is None or not re.match(params["pattern"], str(value))
            if kind == "in_set":
                return value is None or str(value) not in set(params["values"])
            if kind == "not_negative":
                return value is not None and value < 0
            if kind == "reference_lookup":
                return value is not None and value not in set(params["valid_values"])
            raise ValueError(f"unsupported sample kind: {kind!r}")

        samples: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            value = row.get(column)
            if fails(value):
                samples.append({"record_id": index, "actual_value": value})
                if len(samples) >= limit:
                    break
        return samples

    def _extract_table_from_sql(self, sql: str) -> str | None:
        match = re.search(r"FROM\s+(\S+)", sql, re.IGNORECASE)
        return match.group(1) if match else None
