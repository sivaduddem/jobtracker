"""Send a Telegram digest of currently active internships.

Usage (local):
  set TELEGRAM_* in .env, ensure data/internships.db exists
  python scripts/telegram_openings.py

Usage (Actions): see .github/workflows/digest-openings.yml
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.config import get_settings  # noqa: E402
from database.sqlite import Storage  # noqa: E402


def _chunk(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > limit and buf:
            parts.append("".join(buf))
            buf = [line]
            size = len(line)
        else:
            buf.append(line)
            size += len(line)
    if buf:
        parts.append("".join(buf))
    return parts


async def send_digest() -> int:
    settings = get_settings()
    token = (settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (settings.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
        return 1

    storage = Storage(settings.database_path_abs)
    await storage.connect()
    try:
        jobs = await storage.list_internships(
            active_only=True,
            limit=500,
            sort="score",
            descending=True,
        )
    finally:
        await storage.close()

    if not jobs:
        body = "📬 Currently open: none matched (US/Canada SWE intern filters)."
    else:
        lines = [f"📬 Currently open — {len(jobs)} SWE internship(s)\n"]
        for j in jobs:
            loc = j.location or "—"
            lines.append(
                f"• [{int(j.score)}] {j.company} — {j.title}\n"
                f"  {j.term.value} · {loc}\n"
                f"  {j.url}\n"
            )
        body = "\n".join(lines)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession() as session:
        for i, chunk in enumerate(_chunk(body), start=1):
            payload = {
                "chat_id": chat,
                "text": chunk if i == 1 else f"(cont. {i})\n{chunk}",
                "disable_web_page_preview": True,
            }
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    print("Telegram error:", data)
                    return 1
                print(f"Sent chunk {i}, message_id={data['result']['message_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(send_digest()))
