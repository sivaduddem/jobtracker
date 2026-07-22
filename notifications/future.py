"""Future notification channel stubs — Slack, Pushover, ntfy."""

from __future__ import annotations

from core.models import NotificationPayload
from notifications.base import Notifier


class SlackNotifier(Notifier):
    """Webhook-based Slack notifier — implement when webhook URL is configured."""

    name = "slack"

    def enabled(self) -> bool:
        return False

    async def send(self, payload: NotificationPayload) -> bool:
        raise NotImplementedError("Configure SLACK_WEBHOOK_URL to enable")


class PushoverNotifier(Notifier):
    name = "pushover"

    def enabled(self) -> bool:
        return False

    async def send(self, payload: NotificationPayload) -> bool:
        raise NotImplementedError("Configure PUSHOVER_* to enable")


class NtfyNotifier(Notifier):
    name = "ntfy"

    def enabled(self) -> bool:
        return False

    async def send(self, payload: NotificationPayload) -> bool:
        raise NotImplementedError("Configure NTFY_TOPIC to enable")
