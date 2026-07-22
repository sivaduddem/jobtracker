"""
Internship Intelligence Platform — entrypoint.

Usage:
  python main.py                  # run poller + dashboard
  python main.py --once           # single poll cycle then exit
  python main.py --discover       # run company discovery then exit
  python main.py --dashboard-only # serve UI without polling
"""

from __future__ import annotations

import argparse
import asyncio

import aiohttp
import uvicorn

from core.config import get_settings
from core.discovery import DiscoveryEngine
from core.logging import get_logger, setup_logging
from core.scheduler import Scheduler
from dashboard.app import create_app
from database.sqlite import Storage
from notifications import DiscordNotifier, EmailNotifier, NotifierBus, TelegramNotifier
from providers import build_providers

log = get_logger("main")


async def build_runtime() -> tuple[Storage, aiohttp.ClientSession, Scheduler, NotifierBus]:
    settings = get_settings()
    storage = Storage(settings.database_path_abs)
    await storage.connect()

    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=settings.request_timeout_seconds),
        headers={"User-Agent": settings.user_agent},
    )
    providers = build_providers(session)
    notifier = NotifierBus(
        [
            TelegramNotifier(session, settings),
            DiscordNotifier(session, settings),
            EmailNotifier(settings),
        ]
    )
    if notifier.enabled_channels():
        log.info("Notifications enabled: %s", ", ".join(notifier.enabled_channels()))
    else:
        log.warning("No notification channels configured — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID")

    scheduler = Scheduler(storage, session, providers, notifier, settings)
    return storage, session, scheduler, notifier


async def run_discover() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    async with aiohttp.ClientSession() as session:
        engine = DiscoveryEngine(session)
        added = await engine.run()
        log.info("Discovery finished — %d new companies", added)


async def run_once() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    storage, session, scheduler, _ = await build_runtime()
    try:
        if settings.enable_discovery:
            engine = DiscoveryEngine(session)
            await engine.run()
        scheduler.reload_companies()
        await scheduler.run_cycle()
    finally:
        await session.close()
        await storage.close()


async def run_forever(*, dashboard_only: bool = False) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    storage, session, scheduler, _ = await build_runtime()

    # Seed / refresh company registry
    if settings.enable_discovery and not dashboard_only:
        try:
            engine = DiscoveryEngine(session)
            await engine.run()
        except Exception as exc:  # noqa: BLE001
            log.warning("Discovery skipped: %s", exc)

    if not dashboard_only:
        await scheduler.start()

    app = create_app(storage, scheduler)
    config = uvicorn.Config(
        app,
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)

    log.info(
        "Dashboard at http://%s:%d",
        settings.dashboard_host,
        settings.dashboard_port,
    )

    try:
        await server.serve()
    finally:
        server.should_exit = True
        await scheduler.stop()
        await session.close()
        await storage.close()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Internship Intelligence Platform")
    parser.add_argument("--once", action="store_true", help="Run one poll cycle and exit")
    parser.add_argument("--discover", action="store_true", help="Run company discovery and exit")
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Serve dashboard without starting the poller",
    )
    args = parser.parse_args()

    if args.discover:
        asyncio.run(run_discover())
    elif args.once:
        asyncio.run(run_once())
    else:
        # On Windows, signal handlers for SIGTERM may not work; uvicorn still handles Ctrl+C
        try:
            asyncio.run(run_forever(dashboard_only=args.dashboard_only))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    cli()
