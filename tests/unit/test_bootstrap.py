from __future__ import annotations

from pathlib import Path

import pytest

from qualis.adapters.in_memory.adapter import InMemoryAdapter
from qualis.bootstrap import resolve_adapter
from qualis.config.settings import QualisSettings

RULES = Path(__file__).parent.parent / "fixtures" / "rules" / "completeness.yaml"


class TestResolveAdapter:
    def test_builtin_in_memory_resolves(self) -> None:
        settings = QualisSettings(adapter="in_memory", rules_dir=RULES)
        adapter = resolve_adapter(settings)
        assert isinstance(adapter, InMemoryAdapter)

    def test_builtin_duckdb_is_default(self) -> None:
        settings = QualisSettings(rules_dir=RULES)
        adapter = resolve_adapter(settings)
        assert type(adapter).__name__ == "DuckDBAdapter"

    def test_unknown_adapter_lists_known_names(self) -> None:
        settings = QualisSettings(adapter="no_such_engine", rules_dir=RULES)
        with pytest.raises(ValueError, match="no_such_engine") as excinfo:
            resolve_adapter(settings)
        message = str(excinfo.value)
        for known in ("duckdb", "in_memory", "postgres"):
            assert known in message

    def test_entry_point_factory_resolves_by_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import qualis.bootstrap as bootstrap_mod

        sentinel = InMemoryAdapter()

        def fake_load(group: str, protocol: type) -> dict[str, object]:
            assert group == "qualis.adapters"
            return {"thirdparty": lambda settings: sentinel}

        monkeypatch.setattr(bootstrap_mod, "load_entry_points", fake_load)
        settings = QualisSettings(adapter="thirdparty", rules_dir=RULES)
        assert resolve_adapter(settings) is sentinel

    def test_builtin_wins_over_entry_point_shadow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import qualis.bootstrap as bootstrap_mod

        def fake_load(group: str, protocol: type) -> dict[str, object]:
            return {"in_memory": lambda settings: "imposter"}

        monkeypatch.setattr(bootstrap_mod, "load_entry_points", fake_load)
        settings = QualisSettings(adapter="in_memory", rules_dir=RULES)
        assert isinstance(resolve_adapter(settings), InMemoryAdapter)


class TestBuildNotifiers:
    def test_no_urls_configured_yields_empty(self) -> None:
        from qualis.bootstrap import build_notifiers
        from qualis.config.settings import QualisSettings

        settings = QualisSettings(_env_file=None)
        assert build_notifiers(settings) == []

    def test_slack_url_builds_slack_notifier(self) -> None:
        from pydantic import SecretStr

        from qualis.adapters.notifiers import SlackWebhookNotifier
        from qualis.bootstrap import build_notifiers
        from qualis.config.settings import QualisSettings

        settings = QualisSettings(
            _env_file=None,
            slack_webhook_url=SecretStr("https://hooks.slack.com/services/X"),
        )
        notifiers = build_notifiers(settings)
        assert len(notifiers) == 1
        assert isinstance(notifiers[0], SlackWebhookNotifier)

    def test_both_urls_build_both(self) -> None:
        from pydantic import SecretStr

        from qualis.bootstrap import build_notifiers
        from qualis.config.settings import QualisSettings

        settings = QualisSettings(
            _env_file=None,
            slack_webhook_url=SecretStr("https://hooks.slack.com/services/X"),
            webhook_url=SecretStr("https://example.com/hook"),
        )
        assert len(build_notifiers(settings)) == 2

    def test_secret_not_in_settings_repr(self) -> None:
        """SecretStr must mask the webhook URL in any repr/log output."""
        from pydantic import SecretStr

        from qualis.config.settings import QualisSettings

        settings = QualisSettings(
            _env_file=None,
            slack_webhook_url=SecretStr("https://hooks.slack.com/services/SECRET"),
        )
        assert "SECRET" not in repr(settings)

    def test_env_var_resolution(self, monkeypatch) -> None:
        from qualis.config.settings import QualisSettings

        monkeypatch.setenv("QUALIS_WEBHOOK_URL", "https://example.com/from-env")
        settings = QualisSettings(_env_file=None)
        assert settings.webhook_url.get_secret_value() == "https://example.com/from-env"
