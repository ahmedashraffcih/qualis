from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class QualisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUALIS_", env_file=".env")

    database_url: SecretStr = SecretStr("")
    adapter: Literal["duckdb", "in_memory"] = "duckdb"
    rules_dir: Path = Path("rules")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "text"
    dry_run: bool = False
    redact_actual_value: bool = False
    allow_custom: bool = False
