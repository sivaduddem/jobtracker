"""Daily digest — summarize new internships over the last 24h."""

from __future__ import annotations

from datetime import datetime, timedelta

from database.sqlite import Storage
from notifications.base import NotifierBus


async def build_digest_text(storage: Storage, *, hours: int = 24) -> str:
    since = datetime.utcnow() - timedelta(hours=hours)
    jobs = await storage.list_internships(active_only=True, limit=500, sort="first_seen")
    recent = [j for j in jobs if j.first_seen and j.first_seen >= since]
    recent.sort(key=lambda j: (-j.score, j.company))

    if not recent:
        return f"📭 Daily digest — no new internships in the last {hours}h."

    lines = [
        f"📬 Daily digest — {len(recent)} new internship(s) in the last {hours}h",
        "",
    ]
    for j in recent[:40]:
        lines.append(
            f"• [{int(j.score)}] {j.company} — {j.title} ({j.term.value})\n  {j.url}"
        )
    if len(recent) > 40:
        lines.append(f"\n…and {len(recent) - 40} more")
    return "\n".join(lines)


async def send_daily_digest(storage: Storage, notifier: NotifierBus, *, hours: int = 24) -> bool:
    """Send digest via the first enabled channel (Telegram preferred)."""
    text = await build_digest_text(storage, hours=hours)
    # Reuse notification formatting path with a synthetic payload for Telegram text
    for n in notifier.notifiers:
        if not n.enabled():
            continue
        if n.name == "telegram":
            # Send raw digest via Telegram API through format bypass
            from notifications.telegram import TelegramNotifier

            assert isinstance(n, TelegramNotifier)
            url = f"https://api.telegram.org/bot{n.settings.telegram_bot_token}/sendMessage"
            body = {
                "chat_id": n.settings.telegram_chat_id,
                "text": text[:4000],
                "disable_web_page_preview": True,
            }
            async with n.session.post(url, json=body) as resp:
                return resp.status < 400
    return False
