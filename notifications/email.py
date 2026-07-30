"""Email notifier — SMTP alerts for new internship matches."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

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
        return self.settings.email_enabled

    async def send(self, payload: NotificationPayload) -> bool:
        if not self.enabled():
            return False
        return await asyncio.to_thread(self._send_sync, payload)

    def _recipients(self) -> list[str]:
        raw = self.settings.email_to or ""
        parts = [p.strip() for p in raw.replace(";", ",").split(",")]
        return [p for p in parts if p]

    def _send_sync(self, payload: NotificationPayload) -> bool:
        s = self.settings
        recipients = self._recipients()
        if not recipients:
            return False

        job = payload.internship
        subject = f"[Intern Alert] {job.company}: {job.title}"
        text = self.format_text(job, payload.detected_at)
        html = self._format_html(payload)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr(("Internship Intelligence", s.email_username))
        msg["To"] = ", ".join(recipients)
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        try:
            with smtplib.SMTP(s.email_smtp_host, s.email_smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(s.email_username, s.email_password)
                smtp.send_message(msg)
            log.info(
                "Email notified: %s — %s → %s",
                job.company,
                job.title,
                ", ".join(recipients),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Email send failed: %s", exc)
            return False

    def _format_html(self, payload: NotificationPayload) -> str:
        from notifications.base import _eastern

        job = payload.internship
        location = job.location or "N/A"
        time_str = _eastern(payload.detected_at).strftime("%I:%M %p %Z").lstrip("0")
        return f"""\
<html>
  <body style="font-family:Segoe UI,Helvetica,Arial,sans-serif;line-height:1.45;color:#111">
    <h2 style="margin:0 0 12px">New internship</h2>
    <p><strong>Company:</strong> {job.company}<br/>
       <strong>Title:</strong> {job.title}<br/>
       <strong>Term:</strong> {job.term.value}<br/>
       <strong>Location:</strong> {location}<br/>
       <strong>Detected:</strong> {time_str}<br/>
       <strong>Provider:</strong> {job.provider.value.title()}<br/>
       <strong>Score:</strong> {int(job.score)}</p>
    <p><a href="{job.url}" style="display:inline-block;padding:10px 16px;background:#111;color:#fff;text-decoration:none;border-radius:6px">Open posting</a></p>
    <p style="color:#555;font-size:12px">{job.url}</p>
  </body>
</html>
"""
