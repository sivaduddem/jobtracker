"""Uber Careers adapter — official loadSearchJobsResults JSON API.

POST https://www.uber.com/api/loadSearchJobsResults?localeCode=en
Body: { query, page, params: { location: [{country: USA|CAN}, ...] } }
"""

from __future__ import annotations

import re
from typing import Any

import aiohttp

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider

API = "https://www.uber.com/api/loadSearchJobsResults?localeCode=en"
JOB_BASE = "https://www.uber.com/careers/list"
INTERN_RE = re.compile(r"\bintern(?:ship)?\b", re.IGNORECASE)


class UberProvider(BaseProvider):
    name = ATSProvider.UBER

    async def fetch(self, company: CompanyConfig) -> PollResult:
        queries = company.metadata.get("search_queries") or [
            "Software Engineer Intern",
            "Software Engineering Intern",
            "SWE Intern",
        ]
        countries = company.metadata.get("countries") or ["USA", "CAN"]
        max_pages = int(company.metadata.get("max_pages") or 5)

        seen: dict[str, dict[str, Any]] = {}
        last_error: str | None = None

        for query in queries:
            for page in range(max_pages):
                body = {
                    "params": {
                        "location": [{"country": c} for c in countries],
                        "department": [],
                        "team": [],
                        "programAndPlatform": [],
                        "lineOfBusinessDept": [],
                    },
                    "query": str(query),
                    "page": page,
                }
                try:
                    timeout = aiohttp.ClientTimeout(
                        total=self.settings.request_timeout_seconds
                    )
                    async with self.session.post(
                        API,
                        json=body,
                        headers={
                            "User-Agent": self.settings.user_agent,
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "x-csrf-token": "x",
                        },
                        timeout=timeout,
                    ) as resp:
                        if resp.status >= 400:
                            last_error = f"HTTP {resp.status}"
                            break
                        data = await resp.json(content_type=None)
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    break

                if not isinstance(data, dict) or data.get("status") != "success":
                    last_error = f"unexpected response: {str(data)[:200]}"
                    break

                payload = data.get("data") or {}
                results = payload.get("results") or []
                if not results:
                    break
                for job in results:
                    title = job.get("title") or ""
                    title_l = title.lower()
                    if not INTERN_RE.search(title):
                        continue
                    # Drop non-engineering when query is broad
                    if not any(
                        t in title_l
                        for t in (
                            "software",
                            "engineer",
                            "swe",
                            "backend",
                            "frontend",
                            "full stack",
                            "fullstack",
                            "infrastructure",
                            "platform",
                            "security",
                            "machine learning",
                            "ml ",
                            "data engineer",
                        )
                    ):
                        continue
                    job_id = str(job.get("id") or "")
                    if not job_id or job_id in seen:
                        continue
                    seen[job_id] = job

                # Uber may return a large first page; stop when exhausted
                if page == 0 and len(results) < 20:
                    break
                if page > 0 and not results:
                    break
                if len(results) < 10:
                    break

        if not seen and last_error:
            return PollResult(
                company=company.slug,
                provider=self.name,
                error=last_error,
            )

        internships = [self._normalize(company, j) for j in seen.values()]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        job_id = str(job.get("id") or "")
        loc = job.get("location") or {}
        if isinstance(loc, dict):
            parts = [loc.get("city"), loc.get("region"), loc.get("country")]
            location = ", ".join(p for p in parts if p)
        else:
            location = str(loc) if loc else None

        # Public job detail URL pattern used by Uber careers
        url = f"{JOB_BASE}/{job_id}" if job_id else JOB_BASE

        return Internship(
            company=company.display_name,
            title=job.get("title") or "Untitled",
            location=location,
            url=url,
            job_id=job_id,
            provider=self.name,
            description=job.get("description"),
            source="uber",
            raw=job,
        )
