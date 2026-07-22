"""Lever postings API adapter.

Public API: https://api.lever.co/v0/postings/{site}?mode=json
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class LeverProvider(BaseProvider):
    name = ATSProvider.LEVER

    def board_url(self, token: str) -> str:
        return f"https://api.lever.co/v0/postings/{token}"

    async def fetch(self, company: CompanyConfig) -> PollResult:
        token = company.board_token or company.slug
        etag = company.metadata.get("_etag")
        url = self.board_url(token)

        data, status, headers = await self.get_json(
            url,
            etag=etag,
            last_modified=company.metadata.get("_last_modified"),
            params={"mode": "json"},
        )
        etag_out, last_mod_out = self.extract_cache_headers(headers)

        if status == 304:
            return PollResult(
                company=company.slug,
                provider=self.name,
                not_modified=True,
                etag=etag_out or etag,
                last_modified=last_mod_out,
            )

        jobs_raw = data if isinstance(data, list) else []
        internships = [self._normalize(company, job) for job in jobs_raw]

        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
            etag=etag_out,
            last_modified=last_mod_out,
        )

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        categories = job.get("categories") or {}
        location = categories.get("location") or job.get("workplaceType")
        if isinstance(job.get("location"), str):
            location = job["location"]

        posted = None
        created = job.get("createdAt")
        if isinstance(created, (int, float)):
            # Lever uses epoch milliseconds
            ts = created / 1000 if created > 1e12 else created
            posted = datetime.fromtimestamp(ts, tz=timezone.utc)

        remote = None
        wt = (job.get("workplaceType") or "").lower()
        if wt == "remote" or (isinstance(location, str) and "remote" in location.lower()):
            remote = True

        description = None
        if isinstance(job.get("description"), str):
            description = job["description"]
        elif isinstance(job.get("descriptionPlain"), str):
            description = job["descriptionPlain"]

        return Internship(
            company=company.display_name,
            title=job.get("text") or job.get("title") or "Untitled",
            location=location,
            url=job.get("hostedUrl") or job.get("applyUrl") or "",
            job_id=str(job.get("id", "")),
            provider=self.name,
            posted_date=posted,
            employment_type=categories.get("commitment"),
            remote=remote,
            description=description,
            source="lever",
            raw=job,
        )
