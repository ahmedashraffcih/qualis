"""Notifier adapters — see webhook.py for the failure-semantics contract."""

from qualis.adapters.notifiers.webhook import (
    SlackWebhookNotifier,
    WebhookNotifier,
    dispatch_notifications,
)

__all__ = [
    "SlackWebhookNotifier",
    "WebhookNotifier",
    "dispatch_notifications",
]
