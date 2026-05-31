from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qualis.adapters.duckdb.adapter import DuckDBAdapter
from qualis.adapters.in_memory.adapter import InMemoryAdapter
from qualis.config.loader import load_rules_from_path
from qualis.domain.enums import DQDimension
from qualis.engine.checker import CheckRunner

if TYPE_CHECKING:
    from pathlib import Path

    from qualis.config.settings import QualisSettings


def create_checker(settings: QualisSettings, sample_path: Path | None = None) -> CheckRunner:
    """Construct a :class:`CheckRunner` wired to the right adapter.

    When *sample_path* is provided the file is registered in a fresh
    :class:`DuckDBAdapter` and the table name is derived from the stem.
    Otherwise the adapter is chosen from *settings.adapter*.
    """
    adapter: Any
    if sample_path is not None:
        adapter = DuckDBAdapter()
        if sample_path.suffix == ".csv":
            adapter.register_csv(sample_path.stem, sample_path)
        elif sample_path.suffix == ".parquet":
            adapter.register_parquet(sample_path.stem, sample_path)
    elif settings.adapter == "in_memory":
        adapter = InMemoryAdapter()
    elif settings.adapter == "postgres":
        from qualis.adapters.postgres.adapter import PostgresAdapter

        adapter = PostgresAdapter(settings.database_url.get_secret_value())
    else:
        adapter = DuckDBAdapter()

    rules = load_rules_from_path(settings.rules_dir)
    weights: dict[DQDimension, float] = {
        DQDimension.COMPLETENESS: 0.40,
        DQDimension.VALIDITY: 0.35,
        DQDimension.UNIQUENESS: 0.25,
    }
    return CheckRunner(
        adapter=adapter,
        rules=rules,
        weights=weights,
        redact=settings.redact_actual_value,
    )
