"""Greenhouse Job Board API adapter.

Public API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs
No auth required for public boards. Supports ETag.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class GreenhouseProvider(BaseProvider):
    name = ATSProvider.GREENHOUSE

    def board_url(self, token: str) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

    async def fetch(self, company: CompanyConfig) -> PollResult:
        token = company.board_token or company.slug
        etag = company.metadata.get("_etag")
        last_mod = company.metadata.get("_last_modified")
        url = self.board_url(token)

        data, status, headers = await self.get_json(
            url,
            etag=etag,
            last_modified=last_mod,
            params={"content": "true"},
        )
        etag_out, last_mod_out = self.extract_cache_headers(headers)

        if status == 304:
            return PollResult(
                company=company.slug,
                provider=self.name,
                not_modified=True,
                etag=etag_out or etag,
                last_modified=last_mod_out or last_mod,
            )

        jobs_raw = (data or {}).get("jobs", []) if isinstance(data, dict) else []
        internships: list[Internship] = []
        for job in jobs_raw:
            internships.append(self._normalize(company, job))

        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
            etag=etag_out,
            last_modified=last_mod_out,
        )

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        loc = job.get("location", {})
        location = loc.get("name") if isinstance(loc, dict) else str(loc or "")
        offices = job.get("offices") or []
        if not location and offices:
            location = ", ".join(
                o.get("name", "") for o in offices if isinstance(o, dict) and o.get("name")
            )

        absolute_url = job.get("absolute_url") or (
            f"https://boards.greenhouse.io/{company.board_token or company.slug}/jobs/{job.get('id')}"
        )
        posted = None
        if job.get("updated_at"):
            try:
                posted = datetime.fromisoformat(job["updated_at"].replace("Z", "+00:00"))
            except ValueError:
                posted = None

        remote = None
        loc_l = (location or "").lower()
        if "remote" in loc_l:
            remote = True

        return Internship(
            company=company.display_name,
            title=job.get("title") or "Untitled",
            location=location or None,
            url=absolute_url,
            job_id=str(job.get("id", "")),
            provider=self.name,
            posted_date=posted,
            employment_type=(job.get("metadata") or [{}])[0].get("value")
            if isinstance(job.get("metadata"), list) and job.get("metadata")
            else None,
            remote=remote,
            description=job.get("content"),
            source="greenhouse",
            raw=job,
        )
