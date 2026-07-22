"""
Provider base interface.

Every ATS adapter implements BaseProvider.fetch(). Adding a new ATS requires:
  1. Subclass BaseProvider
  2. Register in providers/__init__.py PROVIDER_REGISTRY
  3. Add companies to companies.yaml with that provider key
"""

from __future__ import annotations

import asyncio
import random
import time
from abc import ABC, abstractmethod
from typing import Any

import aiohttp

from core.config import get_settings
from core.logging import get_logger
from core.models import ATSProvider, CompanyConfig, Internship, PollResult

log = get_logger("providers.base")


class BaseProvider(ABC):
    """Abstract ATS adapter. Prefer JSON/GraphQL; HTML only as fallback."""

    name: ATSProvider
    # Optional Playwright fallback flag — subclasses set True only if needed
    requires_browser: bool = False

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.settings = get_settings()

    @abstractmethod
    async def fetch(self, company: CompanyConfig) -> PollResult:
        """Fetch and normalize all internship-relevant jobs for a company."""

    async def get_json(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any | None, int, dict[str, str]]:
        """
        GET JSON with conditional request support.
        Returns (body_or_None, status, response_headers).
        304 => body is None, not_modified path.
        """
        req_headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "application/json, text/plain, */*",
        }
        if headers:
            req_headers.update(headers)
        if etag:
            req_headers["If-None-Match"] = etag
        if last_modified:
            req_headers["If-Modified-Since"] = last_modified

        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        async with self.session.get(
            url, params=params, headers=req_headers, timeout=timeout
        ) as resp:
            resp_headers = {k: v for k, v in resp.headers.items()}
            if resp.status == 304:
                return None, 304, resp_headers
            if resp.status >= 400:
                text = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=text[:500],
                    headers=resp.headers,
                )
            # Some ATS return HTML error pages with 200 — callers validate
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type or url.endswith(".json"):
                data = await resp.json(content_type=None)
            else:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = await resp.text()
            return data, resp.status, resp_headers

    async def get_text(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[str | None, int, dict[str, str]]:
        req_headers = {"User-Agent": self.settings.user_agent}
        if headers:
            req_headers.update(headers)
        if etag:
            req_headers["If-None-Match"] = etag
        if last_modified:
            req_headers["If-Modified-Since"] = last_modified

        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        async with self.session.get(url, headers=req_headers, timeout=timeout) as resp:
            resp_headers = {k: v for k, v in resp.headers.items()}
            if resp.status == 304:
                return None, 304, resp_headers
            if resp.status >= 400:
                text = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=text[:500],
                    headers=resp.headers,
                )
            return await resp.text(), resp.status, resp_headers

    async def fetch_with_retry(
        self,
        company: CompanyConfig,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> PollResult:
        """Exponential backoff wrapper around fetch()."""
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            started = time.perf_counter()
            try:
                # Jitter to avoid thundering herd across thousands of companies
                await asyncio.sleep(random.uniform(0.05, 0.4))
                result = await self.fetch(company)
                result.duration_ms = (time.perf_counter() - started) * 1000
                if attempt > 0:
                    log.info("Recovered %s/%s after %d retries", company.slug, self.name, attempt)
                return result
            except Exception as exc:  # noqa: BLE001 — providers surface errors via PollResult
                last_exc = exc
                delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                log.warning(
                    "Retrying %s/%s (attempt %d/%d): %s",
                    company.slug,
                    self.name.value,
                    attempt + 1,
                    max_retries,
                    exc,
                )
                await asyncio.sleep(delay)

        return PollResult(
            company=company.slug,
            provider=self.name,
            error=str(last_exc) if last_exc else "unknown error",
        )

    @staticmethod
    def extract_cache_headers(headers: dict[str, str]) -> tuple[str | None, str | None]:
        etag = headers.get("ETag") or headers.get("etag")
        last_mod = headers.get("Last-Modified") or headers.get("last-modified")
        return etag, last_mod
