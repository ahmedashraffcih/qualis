"""Webhook notifiers — the first ``NotifierPort`` implementations.

Two failure-semantics rules govern this module (qualis#20, AgDR-0007):

1. **A notifier can never fail the check run.** The supported entry point
   is :func:`dispatch_notifications`, which isolates each notifier in its
   own try/except and logs a warning on failure — the same shape as the
   rule engine's sampling fallback. Calling ``notify_results`` directly
   bypasses that isolation; don't.
2. **Secrets never live in YAML.** Webhook URLs arrive via
   ``QualisSettings`` env fields (``QUALIS_SLACK_WEBHOOK_URL`` /
   ``QUALIS_WEBHOOK_URL``) — there is no YAML surface for them at all.

Payloads are summaries (dataset, score, violation counts, up to
``MAX_PAYLOAD_DIMENSIONS`` worst dimensions) — never violation samples,
which both respects Slack's message-size cap and keeps row-level data
out of third-party channels.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Final
from urllib.parse import urlparse
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qualis.domain.models import DatasetScore
    from qualis.ports.notifier import NotifierPort

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S: Final[float] = 10.0
"""Hard cap on each webhook POST — a hanging endpoint costs at most this."""

MAX_PAYLOAD_DIMENSIONS: Final[int] = 10
"""Worst-N dimensions included in a payload; the rest are summarized away."""


def _validated_url(url: str) -> str:
    """Reject any URL whose scheme is not http(s).

    ``urlopen`` follows whatever scheme it is given (``file://``,
    ``ftp://``...); constraining at construction time turns a
    misconfigured env var into an immediate, located error instead of a
    surprising local-file read at notify time.
    """
    scheme = urlparse(url).scheme
    if scheme not in {"http", "https"}:
        raise ValueError(
            f"notifier URL must use http(s) scheme, got {scheme or 'none'!r}"
        )
    return url


def _summary(score: DatasetScore) -> dict[str, object]:
    """Bounded, sample-free summary of a ``DatasetScore``."""
    worst = sorted(score.dimension_scores, key=lambda d: d.score)
    return {
        "dataset": score.dataset,
        "aggregate_score_pct": int(score.aggregate_score * 100),
        "total_violations": score.total_violations,
        "critical_violations": score.critical_violations,
        "dimensions": [
            {
                "dimension": d.dimension.value,
                "score_pct": int(d.score * 100),
                "passed": d.passed,
                "failed": d.failed,
            }
            for d in worst[:MAX_PAYLOAD_DIMENSIONS]
        ],
    }


class WebhookNotifier:
    """POST the score summary as JSON to a generic webhook endpoint."""

    def __init__(self, url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._url = _validated_url(url)
        self._timeout_s = timeout_s

    def _body(self, score: DatasetScore) -> bytes:
        return json.dumps(_summary(score)).encode("utf-8")

    def notify_results(self, score: DatasetScore) -> None:
        request = Request(
            self._url,
            data=self._body(score),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Single attempt, no retry (v1): non-2xx raises HTTPError, which
        # the dispatcher logs. urlopen's timeout bounds the whole exchange.
        with urlopen(request, timeout=self._timeout_s):
            pass


class SlackWebhookNotifier(WebhookNotifier):
    """POST a Slack-formatted ``{"text": ...}`` summary to a Slack webhook."""

    def _body(self, score: DatasetScore) -> bytes:
        s = _summary(score)
        dims = s["dimensions"]
        assert isinstance(dims, list)
        worst = ", ".join(
            f"{d['dimension']} {d['score_pct']}" for d in dims[:3] if d["failed"]
        )
        text = (
            f"qualis: *{s['dataset']}* scored {s['aggregate_score_pct']}/100 — "
            f"{s['total_violations']} violation(s), "
            f"{s['critical_violations']} critical."
        )
        if worst:
            text += f" Worst dimensions: {worst}."
        return json.dumps({"text": text}).encode("utf-8")


def dispatch_notifications(
    notifiers: Iterable[NotifierPort], score: DatasetScore
) -> None:
    """Run every notifier, isolating each failure to a logged warning.

    This is the supported entry point: a dead endpoint, a DNS failure, a
    timeout, or a 500 must never change the check run's outcome. Each
    notifier gets its own try/except so one failure can't block the rest.
    """
    for notifier in notifiers:
        try:
            notifier.notify_results(score)
        except Exception as exc:
            logger.warning(
                "notification via %s failed (%s); check run unaffected",
                type(notifier).__name__,
                exc,
            )
