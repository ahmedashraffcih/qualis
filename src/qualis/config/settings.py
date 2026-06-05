from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class QualisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUALIS_", env_file=".env")

    database_url: SecretStr = SecretStr("")
    # Adapter NAME — resolved by qualis.bootstrap.resolve_adapter against
    # built-ins (duckdb / in_memory / postgres / sqlalchemy) plus the
    # `qualis.adapters` entry-point group, so the value space is open.
    # Unknown names fail at resolution with the full list of known names.
    adapter: str = "duckdb"
    rules_dir: Path = Path("rules")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "text"
    dry_run: bool = False
    redact_actual_value: bool = False
    allow_custom: bool = False
    # Server-side per-statement timeout for check queries, in milliseconds.
    # Applied by adapters that support it (Postgres via SET LOCAL); DuckDB
    # has no per-statement timeout and ignores this. None = server default.
    statement_timeout_ms: int | None = None
