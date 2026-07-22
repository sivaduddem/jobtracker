"""Notification formatting / Telegram payload tests."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models import ATSProvider, Internship, InternshipTerm, NotificationPayload
from notifications.base import NullNotifier
from notifications.telegram import TelegramNotifier


def test_format_text_contains_fields():
    job = Internship(
        company="Databricks",
        title="Software Engineer Intern",
        location="Mountain View, CA",
        url="https://example.com/apply",
        job_id="42",
        provider=ATSProvider.GREENHOUSE,
        term=InternshipTerm.SUMMER_2027,
        score=98,
    )
    text = NullNotifier().format_text(job, datetime(2026, 7, 21, 18, 13))
    assert "NEW INTERNSHIP" in text
    assert "Databricks" in text
    assert "Software Engineer Intern" in text
    assert "Summer 2027" in text
    assert "Mountain View, CA" in text
    assert "Greenhouse" in text
    assert "98" in text
    assert "https://example.com/apply" in text


@pytest.mark.asyncio
async def test_telegram_disabled_without_creds():
    session = MagicMock()
    settings = MagicMock()
    settings.telegram_enabled = False
    settings.telegram_bot_token = ""
    settings.telegram_chat_id = ""
    n = TelegramNotifier(session, settings)  # type: ignore[arg-type]
    assert not n.enabled()
    ok = await n.send(
        NotificationPayload(
            internship=Internship(
                company="X",
                title="SWE Intern",
                url="https://x.com",
                job_id="1",
                provider=ATSProvider.LEVER,
            )
        )
    )
    assert ok is False


@pytest.mark.asyncio
async def test_telegram_send_posts_message():
    session = MagicMock()
    resp = AsyncMock()
    resp.status = 200
    resp.text = AsyncMock(return_value="{}")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=resp)

    settings = MagicMock()
    settings.telegram_enabled = True
    settings.telegram_bot_token = "token"
    settings.telegram_chat_id = "123"

    n = TelegramNotifier(session, settings)  # type: ignore[arg-type]
    job = Internship(
        company="Databricks",
        title="Software Engineer Intern",
        url="https://example.com/apply",
        job_id="42",
        provider=ATSProvider.GREENHOUSE,
        term=InternshipTerm.SUMMER_2027,
        score=98,
    )
    ok = await n.send(NotificationPayload(internship=job))
    assert ok is True
    session.post.assert_called_once()
    args, kwargs = session.post.call_args
    assert "sendMessage" in args[0]
    assert kwargs["json"]["chat_id"] == "123"
    assert "inline_keyboard" in kwargs["json"]["reply_markup"]
