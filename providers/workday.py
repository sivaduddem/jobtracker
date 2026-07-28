"""Workday Career Site adapter.

board_token format: "tenant:site"  e.g. "nvidia:NVIDIAExternalCareerSite"
Public CXS API:
  https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
"""

from __future__ import annotations

import re
from typing import Any

import aiohttp

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider
from core.logging import get_logger

log = get_logger("providers.workday")

# Common Workday host suffixes to try when only tenant:site is known
_WD_HOSTS = ["wd1", "wd3", "wd5", "wd12", "wd501"]


class WorkdayProvider(BaseProvider):
    name = ATSProvider.WORKDAY

    def _parse_token(self, company: CompanyConfig) -> tuple[str, str, str | None]:
        """Return (tenant, site, host_override)."""
        token = company.board_token or company.slug
        host = company.metadata.get("workday_host")
        if ":" in token:
            tenant, site = token.split(":", 1)
            return tenant, site, host
        # career_url may embed full path
        if company.career_url:
            m = re.search(
                r"https?://([a-z0-9_-]+)\.(wd\d+)\.myworkdayjobs\.com/([^/?#]+)",
                company.career_url,
                re.I,
            )
            if m:
                return m.group(1), m.group(3), m.group(2)
        return token, "External", host

    async def fetch(self, company: CompanyConfig) -> PollResult:
        tenant, site, host = self._parse_token(company)
        jobs: list[dict[str, Any]] = []
        last_error: str | None = None
        hosts = [host] if host else _WD_HOSTS

        for h in hosts:
            if not h:
                continue
            url = f"https://{tenant}.{h}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
            try:
                page = 0
                while True:
                    body = {
                        "appliedFacets": {},
                        "limit": 20,
                        "offset": page * 20,
                        "searchText": "intern",
                    }
                    timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
                    async with self.session.post(
                        url,
                        json=body,
                        headers={
                            "User-Agent": self.settings.user_agent,
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                        },
                        timeout=timeout,
                    ) as resp:
                        if resp.status >= 400:
                            last_error = f"HTTP {resp.status}"
                            break
                        data = await resp.json(content_type=None)

                    batch = data.get("jobPostings") or []
                    jobs.extend(batch)
                    total = data.get("total", len(jobs))
                    if len(jobs) >= total or not batch:
                        break
                    page += 1
                    if page > 50:  # safety
                        break

                if jobs or last_error is None:
                    # Persist working host for next time
                    company.metadata["workday_host"] = h
                    last_error = None
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue

        if last_error and not jobs:
            return PollResult(
                company=company.slug,
                provider=self.name,
                error=last_error,
            )

        internships = [
            self._normalize(company, job, tenant, site, company.metadata.get("workday_host", "wd5"))
            for job in jobs
        ]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )

    def _normalize(
        self,
        company: CompanyConfig,
        job: dict[str, Any],
        tenant: str,
        site: str,
        host: str,
    ) -> Internship:
        title = job.get("title") or job.get("externalPath") or "Untitled"
        path = job.get("externalPath") or ""
        url = f"https://{tenant}.{host}.myworkdayjobs.com/{site}{path}"
        locations = job.get("locationsText") or job.get("bulletFields")
        location = None
        if isinstance(locations, str):
            location = locations
        elif isinstance(locations, list):
            location = ", ".join(str(x) for x in locations)

        job_id = str(job.get("bulletFields", [""])[0] if isinstance(job.get("bulletFields"), list) else "")
        if not job_id:
            job_id = path or title

        return Internship(
            company=company.display_name,
            title=title,
            location=location,
            url=url,
            job_id=job_id,
            provider=self.name,
            remote=("remote" in (location or "").lower()) or None,
            description=job.get("jobPostingInfo", {}).get("jobDescription")
            if isinstance(job.get("jobPostingInfo"), dict)
            else None,
            source="workday",
            raw=job,
        )
