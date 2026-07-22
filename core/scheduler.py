"""Async adaptive scheduler — polls thousands of companies concurrently."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import aiohttp

from core.config import Settings, get_settings, load_companies
from core.logging import get_logger
from core.models import CompanyConfig, CompanyState, PollResult
from core.prediction import (
    compute_poll_interval,
    is_company_hot,
    predict_hot_companies,
)
from core.ranking import enrich_internship
from database.sqlite import Storage
from notifications.base import NotifierBus

if TYPE_CHECKING:
    from core.provider_base import BaseProvider

log = get_logger("scheduler")


def apply_adaptive_schedule(
    state: CompanyState,
    *,
    interval: int,
    now: datetime,
) -> bool:
    """
    Update poll_interval_seconds and next_poll_at for the current adaptive interval.

    Returns True if the company is due to poll at `now`.

    If the interval shortens (hot window / business hours), pull an overly distant
    next_poll_at forward so the new cadence takes effect immediately instead of
    waiting out a stale long deadline from a prior poll.
    """
    state.poll_interval_seconds = interval
    if state.next_poll_at is None:
        state.next_poll_at = now
    else:
        latest_allowed = now + timedelta(seconds=interval)
        if state.next_poll_at > latest_allowed:
            state.next_poll_at = latest_allowed
    return state.next_poll_at <= now


class Scheduler:
    def __init__(
        self,
        storage: Storage,
        session: aiohttp.ClientSession,
        providers: dict[str, BaseProvider],
        notifier: NotifierBus,
        settings: Settings | None = None,
    ) -> None:
        self.storage = storage
        self.session = session
        self.providers = providers
        self.notifier = notifier
        self.settings = settings or get_settings()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._sem = asyncio.Semaphore(self.settings.max_concurrent_polls)
        self.companies: list[CompanyConfig] = []
        self.last_cycle_at: datetime | None = None
        self.cycle_count = 0

    def reload_companies(self) -> None:
        self.companies = [c for c in load_companies() if c.enabled]
        log.info("Loaded %d enabled companies", len(self.companies))

    async def start(self) -> None:
        self.reload_companies()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="scheduler-loop")
        log.info(
            "Scheduler started (%d companies, max concurrency %d)",
            len(self.companies),
            self.settings.max_concurrent_polls,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("Scheduler stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.run_cycle()
            except Exception as exc:  # noqa: BLE001
                log.error("Scheduler cycle failed: %s", exc)
            # Small sleep between cycle planning passes
            await asyncio.sleep(5)

    async def run_cycle(self) -> None:
        """Poll all companies that are due."""
        now = datetime.utcnow()
        history = await self.storage.all_historical()
        hot = predict_hot_companies(history, now=now)

        due: list[CompanyConfig] = []
        for company in self.companies:
            state = await self.storage.get_company_state(company.slug)
            if state is None:
                state = CompanyState(slug=company.slug, provider=company.provider)

            state.predicted_hot = is_company_hot(company, hot)
            interval = compute_poll_interval(company, state, self.settings, now=now)
            if apply_adaptive_schedule(state, interval=interval, now=now):
                due.append(company)

            await self.storage.save_company_state(state)

        if not due:
            return

        log.info("Polling %d/%d companies due", len(due), len(self.companies))

        tasks = [self._poll_one(c) for c in due]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        new_total = 0
        for r in results:
            if isinstance(r, PollResult):
                new_total += r.new_jobs
            elif isinstance(r, Exception):
                log.error("Poll exception: %s", r)

        self.last_cycle_at = datetime.utcnow()
        self.cycle_count += 1
        if new_total:
            log.info("Cycle complete — %d new internships", new_total)

    async def _poll_one(self, company: CompanyConfig) -> PollResult:
        async with self._sem:
            return await self._poll_company(company)

    async def _poll_company(self, company: CompanyConfig) -> PollResult:
        provider = self.providers.get(company.provider.value)
        state = await self.storage.get_company_state(company.slug) or CompanyState(
            slug=company.slug, provider=company.provider
        )

        if provider is None:
            result = PollResult(
                company=company.slug,
                provider=company.provider,
                error=f"No provider adapter for {company.provider.value}",
            )
            state.consecutive_errors += 1
            state.last_error = result.error
            state.next_poll_at = datetime.utcnow() + timedelta(
                seconds=state.poll_interval_seconds or self.settings.poll_inactive
            )
            await self.storage.save_company_state(state)
            return result

        log.info("Checking %s (%s)...", company.display_name, company.provider.value.title())

        # Pass cache headers via company metadata mutation for provider use
        company.metadata = {
            **company.metadata,
            "_etag": state.etag,
            "_last_modified": state.last_modified,
        }

        result = await provider.fetch_with_retry(company)

        if result.error:
            state.consecutive_errors += 1
            state.last_error = result.error
            log.warning("%s error: %s", company.slug, result.error)
        elif result.not_modified:
            state.last_success = datetime.utcnow()
            state.last_error = None
            state.consecutive_errors = 0
            log.info("Found %d jobs (not modified)", state.active_jobs)
        else:
            new_count = 0
            seen_ids: set[str] = set()
            for raw_job in result.internships:
                enriched = enrich_internship(raw_job)
                if enriched is None:
                    continue
                seen_ids.add(enriched.job_id)
                is_new, should_notify = await self.storage.upsert_internship(
                    enriched, notify=True, company_slug=company.slug
                )
                if is_new:
                    new_count += 1
                    if (
                        should_notify
                        and enriched.score >= self.settings.min_notify_score
                    ):
                        await self.notifier.notify(enriched)
                        await self.storage.mark_notified(enriched.dedupe_key)

            removed = await self.storage.mark_missing_inactive(
                company.slug, company.provider, seen_ids
            )
            result.new_jobs = new_count
            result.removed_jobs = removed
            result.total_jobs = len(seen_ids)

            state.last_success = datetime.utcnow()
            state.last_error = None
            state.consecutive_errors = 0
            state.jobs_found_total += new_count
            state.active_jobs = len(seen_ids)
            state.recent_activity = new_count > 0 or removed > 0
            if result.etag:
                state.etag = result.etag
            if result.last_modified:
                state.last_modified = result.last_modified

            log.info(
                "Found %d jobs — %d new%s",
                result.total_jobs,
                new_count,
                f", {removed} removed" if removed else "",
            )

        await self.storage.log_poll(
            company.slug,
            company.provider,
            total_jobs=result.total_jobs,
            new_jobs=result.new_jobs,
            error=result.error,
            duration_ms=result.duration_ms,
            not_modified=result.not_modified,
        )

        now = datetime.utcnow()
        interval = compute_poll_interval(company, state, self.settings, now=now)
        state.poll_interval_seconds = interval
        state.next_poll_at = now + timedelta(
            seconds=int(interval * random.uniform(0.85, 1.15))
        )
        await self.storage.save_company_state(state)
        return result

    async def poll_now(self, slug: str | None = None) -> list[PollResult]:
        """Force-poll one or all companies (dashboard / CLI)."""
        targets = self.companies if slug is None else [c for c in self.companies if c.slug == slug]
        results = await asyncio.gather(*[self._poll_one(c) for c in targets])
        return list(results)
