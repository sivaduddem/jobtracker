"""Send a one-off Telegram test message using .env credentials.

Usage:
  fill TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env
  python scripts/test_telegram.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def main() -> int:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first.")
        return 1

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode(
        {
            "chat_id": chat,
            "text": "Internship Intelligence test: local .env → Telegram is working.",
        }
    ).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())

    if not data.get("ok"):
        print("Telegram API error:", data.get("description"))
        return 1

    print("Sent. message_id =", data["result"]["message_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
