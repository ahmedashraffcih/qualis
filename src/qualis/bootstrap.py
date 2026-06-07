from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qualis.adapters.duckdb.adapter import DuckDBAdapter
from qualis.adapters.in_memory.adapter import InMemoryAdapter
from qualis.config.loader import load_rules_from_path
from qualis.domain.enums import DQDimension
from qualis.engine.checker import CheckRunner
from qualis.plugins import load_entry_points
from qualis.ports.database import DatabasePort

if TYPE_CHECKING:
    from pathlib import Path

    from qualis.config.settings import QualisSettings

# Entry-point group third-party adapter packages register under. The loader
# itself is group-agnostic (qualis.plugins) so future groups — e.g. a
# ``qualis.catalogs`` group for governance-catalog publishers — reuse it.
ADAPTERS_GROUP = "qualis.adapters"

_AdapterFactory = Callable[["QualisSettings"], Any]


def _builtin_factories() -> dict[str, _AdapterFactory]:
    """Factories for the adapters that ship inside qualis core.

    Built-ins always win over an entry point of the same name — a
    third-party package must not be able to silently shadow ``postgres``.
    """

    def _duckdb(settings: QualisSettings) -> Any:
        return DuckDBAdapter()

    def _in_memory(settings: QualisSettings) -> Any:
        return InMemoryAdapter()

    def _postgres(settings: QualisSettings) -> Any:
        from qualis.adapters.postgres.adapter import PostgresAdapter

        return PostgresAdapter(
            settings.database_url.get_secret_value(),
            statement_timeout_ms=settings.statement_timeout_ms,
        )

    # NOTE: the sqlalchemy meta-adapter is deliberately NOT a builtin — it
    # registers through the `qualis.adapters` entry-point group in
    # pyproject.toml, so qualis's own packaging exercises the plugin path
    # end-to-end (AgDR-0004).
    return {
        "duckdb": _duckdb,
        "in_memory": _in_memory,
        "postgres": _postgres,
    }


def resolve_adapter(settings: QualisSettings) -> Any:
    """Resolve ``settings.adapter`` to a constructed ``DatabasePort`` impl.

    Resolution order: built-ins first, then the ``qualis.adapters``
    entry-point group (each entry point is a factory invoked as
    ``factory(settings)``). Unknown names fail with the full set of known
    names so a typo is a one-glance fix.
    """
    builtins = _builtin_factories()
    if settings.adapter in builtins:
        return builtins[settings.adapter](settings)

    plugins = load_entry_points(ADAPTERS_GROUP, DatabasePort)
    if settings.adapter in plugins:
        return plugins[settings.adapter](settings)

    known = sorted(set(builtins) | set(plugins))
    raise ValueError(
        f"Unknown adapter {settings.adapter!r}. "
        f"Known adapters: {', '.join(known)}. "
        f"Third-party adapters register via the {ADAPTERS_GROUP!r} "
        f"entry-point group."
    )


def create_checker(
    settings: QualisSettings,
    sample_path: Path | None = None,
    sample_rows: int | None = None,
) -> CheckRunner:
    """Construct a :class:`CheckRunner` wired to the right adapter.

    When *sample_path* is provided the file is registered in a fresh
    :class:`DuckDBAdapter` and the table name is derived from the stem.
    Otherwise the adapter is resolved from *settings.adapter* via
    :func:`resolve_adapter` (built-ins + entry-point plugins).
    """
    adapter: Any
    if sample_path is not None:
        adapter = DuckDBAdapter()
        if sample_path.suffix == ".csv":
            adapter.register_csv(sample_path.stem, sample_path)
        elif sample_path.suffix == ".parquet":
            adapter.register_parquet(sample_path.stem, sample_path)
    else:
        adapter = resolve_adapter(settings)

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
        sample_rows=sample_rows,
    )


def build_notifiers(settings: QualisSettings) -> list[Any]:
    """Construct the notifiers whose endpoints are configured.

    Endpoints arrive ONLY via env-backed ``SecretStr`` settings
    (``QUALIS_SLACK_WEBHOOK_URL`` / ``QUALIS_WEBHOOK_URL``) — see
    AgDR-0007. Empty string = not configured = skipped. The returned
    list feeds ``dispatch_notifications``, never direct calls.
    """
    from qualis.adapters.notifiers import SlackWebhookNotifier, WebhookNotifier

    notifiers: list[Any] = []
    slack_url = settings.slack_webhook_url.get_secret_value()
    if slack_url:
        notifiers.append(SlackWebhookNotifier(slack_url))
    generic_url = settings.webhook_url.get_secret_value()
    if generic_url:
        notifiers.append(WebhookNotifier(generic_url))
    return notifiers
