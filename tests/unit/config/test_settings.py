from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from qualis.config.settings import QualisSettings


def test_defaults() -> None:
    settings = QualisSettings()
    assert settings.adapter == "duckdb"
    assert settings.log_level == "INFO"
    assert settings.log_format == "text"
    assert settings.dry_run is False
    assert settings.redact_actual_value is False
    assert settings.allow_custom is False
    assert settings.rules_dir == Path("rules")


def test_database_url_is_secret_str() -> None:
    settings = QualisSettings(database_url="postgresql://user:secret@localhost/db")  # type: ignore[arg-type]
    # SecretStr repr must not expose the raw value
    assert "**" in repr(settings.database_url)
    assert "secret" not in repr(settings.database_url)


def test_database_url_empty_by_default() -> None:
    settings = QualisSettings()
    # Empty SecretStr has no value to redact; confirm it is a SecretStr instance
    assert "SecretStr" in repr(settings.database_url)
    # The raw value must NOT be directly accessible via repr
    assert "postgresql" not in repr(settings.database_url)


def test_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUALIS_LOG_LEVEL", "DEBUG")
    settings = QualisSettings()
    assert settings.log_level == "DEBUG"


def test_env_var_adapter_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUALIS_ADAPTER", "in_memory")
    settings = QualisSettings()
    assert settings.adapter == "in_memory"


def test_env_var_dry_run_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUALIS_DRY_RUN", "true")
    settings = QualisSettings()
    assert settings.dry_run is True
