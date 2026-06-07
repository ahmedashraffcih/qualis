from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from qualis.adapters.notifiers import (
    SlackWebhookNotifier,
    WebhookNotifier,
    dispatch_notifications,
)
from qualis.domain.enums import DQDimension
from qualis.domain.models import DatasetScore, DimensionScore


def make_score(*, n_dimensions: int = 2, aggregate: float = 0.83) -> DatasetScore:
    dims = [
        DimensionScore(
            dimension=list(DQDimension)[i % len(list(DQDimension))],
            dataset="orders",
            total_checks=10,
            passed=8,
            failed=2,
            score=0.5 + (i * 0.01),
        )
        for i in range(n_dimensions)
    ]
    return DatasetScore(
        dataset="orders",
        dimension_scores=dims,
        aggregate_score=aggregate,
        total_violations=42,
        critical_violations=3,
    )


class _CapturedRequest:
    """What the patched urlopen saw."""

    def __init__(self) -> None:
        self.url: str | None = None
        self.body: bytes | None = None
        self.timeout: float | None = None
        self.headers: dict[str, str] = {}


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> _CapturedRequest:
    cap = _CapturedRequest()

    class _FakeResponse:
        status = 200

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        cap.url = req.full_url
        cap.body = req.data
        cap.timeout = timeout
        cap.headers = dict(req.header_items())
        return _FakeResponse()

    monkeypatch.setattr("qualis.adapters.notifiers.webhook.urlopen", fake_urlopen)
    return cap


class TestWebhookNotifier:
    def test_posts_json_summary(self, captured: _CapturedRequest) -> None:
        WebhookNotifier("https://example.com/hook").notify_results(make_score())
        assert captured.url == "https://example.com/hook"
        assert captured.body is not None
        payload = json.loads(captured.body)
        assert payload["dataset"] == "orders"
        assert payload["aggregate_score_pct"] == 83
        assert payload["total_violations"] == 42
        assert payload["critical_violations"] == 3
        assert any("json" in v.lower() for v in captured.headers.values())

    def test_hard_timeout_passed(self, captured: _CapturedRequest) -> None:
        WebhookNotifier("https://example.com/hook", timeout_s=5.0).notify_results(
            make_score()
        )
        assert captured.timeout == 5.0

    def test_default_timeout_is_bounded(self, captured: _CapturedRequest) -> None:
        WebhookNotifier("https://example.com/hook").notify_results(make_score())
        assert captured.timeout is not None
        assert captured.timeout <= 10.0

    def test_payload_dimensions_truncated(self, captured: _CapturedRequest) -> None:
        WebhookNotifier("https://example.com/hook").notify_results(
            make_score(n_dimensions=25)
        )
        assert captured.body is not None
        payload = json.loads(captured.body)
        assert len(payload["dimensions"]) <= 10

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            WebhookNotifier("file:///etc/passwd")

    def test_rejects_empty_url(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            WebhookNotifier("")


class TestSlackWebhookNotifier:
    def test_posts_slack_text_payload(self, captured: _CapturedRequest) -> None:
        SlackWebhookNotifier("https://hooks.slack.com/services/X").notify_results(
            make_score()
        )
        assert captured.body is not None
        payload = json.loads(captured.body)
        assert "text" in payload
        assert "orders" in payload["text"]
        assert "83" in payload["text"]

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            SlackWebhookNotifier("ftp://hooks.slack.com/x")


class _Boom:
    """Notifier that always raises."""

    calls = 0

    def notify_results(self, score: DatasetScore) -> None:
        type(self).calls += 1
        raise ConnectionError("endpoint down")


class _Recorder:
    def __init__(self) -> None:
        self.scores: list[DatasetScore] = []

    def notify_results(self, score: DatasetScore) -> None:
        self.scores.append(score)


class TestDispatchIsolation:
    def test_notifier_failure_never_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            dispatch_notifications([_Boom()], make_score())
        assert any("endpoint down" in r.message for r in caplog.records)

    def test_one_failure_does_not_block_others(self) -> None:
        recorder = _Recorder()
        dispatch_notifications([_Boom(), recorder], make_score())
        assert len(recorder.scores) == 1

    def test_empty_notifier_list_is_noop(self) -> None:
        dispatch_notifications([], make_score())
