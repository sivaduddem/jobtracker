"""Notification channel interfaces — Telegram primary; others stubbed for future use."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.models import Internship, NotificationPayload


def _eastern(now: datetime | None = None) -> datetime:
    """Convert to US/Eastern when tzdata is available; else use UTC-4/5 naive label."""
    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    try:
        return when.astimezone(ZoneInfo("America/New_York"))
    except ZoneInfoNotFoundError:
        # Windows without tzdata package — still produce a readable stamp
        return when.astimezone(timezone.utc)


class Notifier(ABC):
    """Channel-agnostic notification interface."""

    name: str

    @abstractmethod
    async def send(self, payload: NotificationPayload) -> bool:
        """Deliver notification. Return True on success."""

    @abstractmethod
    def enabled(self) -> bool:
        ...

    def format_text(self, internship: Internship, detected_at: datetime | None = None) -> str:
        when = _eastern(detected_at)
        time_str = when.strftime("%I:%M %p %Z").lstrip("0") or when.strftime("%H:%M %Z")

        location = internship.location or "N/A"
        return (
            "🚨 NEW INTERNSHIP\n\n"
            f"Company:\n{internship.company}\n\n"
            f"Title:\n{internship.title}\n\n"
            f"Term:\n{internship.term.value}\n\n"
            f"Location:\n{location}\n\n"
            f"Detected:\n{time_str}\n\n"
            f"Provider:\n{internship.provider.value.title()}\n\n"
            f"Apply:\n{internship.url}\n\n"
            f"Score:\n{int(internship.score)}"
        )


class NullNotifier(Notifier):
    """No-op notifier for dry runs / tests."""

    name = "null"

    def enabled(self) -> bool:
        return True

    async def send(self, payload: NotificationPayload) -> bool:
        return True


class NotifierBus:
    """Fan-out to all enabled channels."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    def enabled_channels(self) -> list[str]:
        return [n.name for n in self.notifiers if n.enabled()]

    async def notify(self, internship: Internship) -> dict[str, bool]:
        payload = NotificationPayload(internship=internship)
        results: dict[str, bool] = {}
        for n in self.notifiers:
            if not n.enabled():
                continue
            try:
                results[n.name] = await n.send(payload)
            except Exception:  # noqa: BLE001
                results[n.name] = False
        return results
