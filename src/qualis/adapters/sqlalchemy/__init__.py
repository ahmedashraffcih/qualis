"""SQLAlchemy meta-adapter package.

The entry point `qualis.adapters → sqlalchemy` resolves to
:func:`create_adapter` below. The factory imports the adapter lazily so the
entry point LOADS cleanly even when the `qualis[sqlalchemy]` extra is not
installed — the helpful ImportError surfaces at construction time instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qualis.config.settings import QualisSettings


def create_adapter(settings: QualisSettings) -> Any:
    """Entry-point factory: build a SQLAlchemyAdapter from settings."""
    from qualis.adapters.sqlalchemy.adapter import SQLAlchemyAdapter

    return SQLAlchemyAdapter(settings.database_url.get_secret_value())
