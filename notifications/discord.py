"""Discord webhook notifier (optional)."""

from __future__ import annotations

import aiohttp

from core.config import Settings, get_settings
from core.logging import get_logger
from core.models import NotificationPayload
from notifications.base import Notifier

log = get_logger("notifications.discord")


class DiscordNotifier(Notifier):
    name = "discord"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        return bool(self.settings.discord_webhook_url)

    async def send(self, payload: NotificationPayload) -> bool:
        if not self.enabled():
            return False
        text = self.format_text(payload.internship, payload.detected_at)
        body = {
            "content": text[:1900],
            "embeds": [
                {
                    "title": payload.internship.title,
                    "url": payload.internship.url,
                    "description": f"{payload.internship.company} · {payload.internship.term.value}",
                    "color": 0xE11D48,
                }
            ],
        }
        async with self.session.post(self.settings.discord_webhook_url, json=body) as resp:
            if resp.status >= 400:
                log.error("Discord send failed: %s", await resp.text())
                return False
            return True
