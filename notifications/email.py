"""Email notifier stub — interface ready, enable via SMTP env vars."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from core.config import Settings, get_settings
from core.logging import get_logger
from core.models import NotificationPayload
from notifications.base import Notifier

log = get_logger("notifications.email")


class EmailNotifier(Notifier):
    name = "email"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        s = self.settings
        return bool(s.email_smtp_host and s.email_username and s.email_password and s.email_to)

    async def send(self, payload: NotificationPayload) -> bool:
        if not self.enabled():
            return False
        return await asyncio.to_thread(self._send_sync, payload)

    def _send_sync(self, payload: NotificationPayload) -> bool:
        s = self.settings
        msg = EmailMessage()
        msg["Subject"] = f"🚨 {payload.internship.company}: {payload.internship.title}"
        msg["From"] = s.email_username
        msg["To"] = s.email_to
        msg.set_content(self.format_text(payload.internship, payload.detected_at))
        try:
            with smtplib.SMTP(s.email_smtp_host, s.email_smtp_port) as smtp:
                smtp.starttls()
                smtp.login(s.email_username, s.email_password)
                smtp.send_message(msg)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Email send failed: %s", exc)
            return False
