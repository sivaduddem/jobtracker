"""Telegram Bot API notifier — primary alert channel."""

from __future__ import annotations

import aiohttp

from core.config import Settings, get_settings
from core.logging import get_logger
from core.models import NotificationPayload
from notifications.base import Notifier

log = get_logger("notifications.telegram")


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        return self.settings.telegram_enabled

    async def send(self, payload: NotificationPayload) -> bool:
        if not self.enabled():
            return False

        text = self.format_text(payload.internship, payload.detected_at)
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        body = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": False,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "Open Posting",
                            "url": payload.internship.url,
                        }
                    ],
                    [
                        {
                            "text": "Dismiss",
                            "callback_data": f"dismiss:{payload.internship.dedupe_key[:40]}",
                        }
                    ],
                ]
            },
        }
        async with self.session.post(url, json=body) as resp:
            if resp.status >= 400:
                err = await resp.text()
                log.error("Telegram send failed (%s): %s", resp.status, err[:300])
                return False
            log.info("Telegram notified: %s — %s", payload.internship.company, payload.internship.title)
            return True
