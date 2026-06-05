"""Group-agnostic entry-point plugin loading.

One loader serves every plugin surface qualis grows: ``qualis.adapters``
today (DatabasePort factories), ``qualis.catalogs`` later (CatalogPort
publishers — see the governance-catalog roadmap). Keeping it generic was a
binding condition of the v0.5.0 design review (C1).
"""

from __future__ import annotations

import importlib.metadata
import inspect
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _protocol_surface(protocol: type[Any]) -> list[str]:
    """Public method names a conforming object must expose."""
    return [
        name
        for name in vars(protocol)
        if not name.startswith("_") and callable(vars(protocol)[name])
    ]


def load_entry_points(group: str, protocol: type[Any]) -> dict[str, Any]:
    """Load every entry point in *group*, keyed by entry-point name.

    Each loaded object is duck-checked against *protocol*'s public surface
    (a ``typing.Protocol`` is not runtime-checkable for structural calls,
    so this is an attribute-presence check, not full conformance). Entry
    points that fail to import or miss the surface are skipped with a
    logged warning — one broken third-party plugin must not take down
    adapter resolution for everyone else.
    """
    required = _protocol_surface(protocol)
    loaded: dict[str, Any] = {}
    for ep in importlib.metadata.entry_points(group=group):
        try:
            obj = ep.load()
        except Exception as exc:
            logger.warning(
                "entry point %r in group %r failed to load: %s — skipped",
                ep.name,
                group,
                exc,
            )
            continue
        if inspect.isclass(obj):
            # Classes are surface-checked eagerly — cheap and catches the
            # common "registered the wrong symbol" mistake at load time.
            missing = [m for m in required if not hasattr(obj, m)]
            if missing:
                logger.warning(
                    "entry point %r in group %r does not satisfy %s "
                    "(missing: %s) — skipped",
                    ep.name,
                    group,
                    protocol.__name__,
                    ", ".join(missing),
                )
                continue
        elif callable(obj):
            # Factory callables (invoked as factory(settings) -> impl) can
            # only be validated after instantiation — accepted here, checked
            # by the caller when invoked.
            logger.debug(
                "entry point %r in group %r is a factory callable; "
                "%s conformance is checked at instantiation",
                ep.name,
                group,
                protocol.__name__,
            )
        else:
            logger.warning(
                "entry point %r in group %r is neither a class nor a "
                "callable — skipped",
                ep.name,
                group,
            )
            continue
        loaded[ep.name] = obj
    return loaded
