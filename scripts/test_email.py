"""Send a one-off test email using EMAIL_* settings from .env."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import get_settings
from core.models import ATSProvider, Internship, InternshipTerm, NotificationPayload
from notifications.email import EmailNotifier


async def main() -> int:
    settings = get_settings()
    notifier = EmailNotifier(settings)
    if not notifier.enabled():
        print(
            "Email is not configured. Set in .env:\n"
            "  EMAIL_SMTP_HOST=smtp.gmail.com\n"
            "  EMAIL_SMTP_PORT=587\n"
            "  EMAIL_USERNAME=sivaduddempudi@gmail.com\n"
            "  EMAIL_PASSWORD=<Gmail App Password>\n"
            "  EMAIL_TO=sivaduddempudi@gmail.com\n"
            "Create an App Password at https://myaccount.google.com/apppasswords"
        )
        return 1

    job = Internship(
        company="Internship Intelligence",
        title="Software Engineer Intern — email test",
        location="Remote - United States",
        url="https://example.com/apply",
        job_id="email-test",
        provider=ATSProvider.GREENHOUSE,
        term=InternshipTerm.SUMMER_2027,
        score=100,
    )
    ok = await notifier.send(NotificationPayload(internship=job))
    if ok:
        print(f"Sent test email to {settings.email_to}")
        return 0
    print("Send failed — check SMTP credentials / App Password")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
