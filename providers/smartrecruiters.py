"""SmartRecruiters public postings API.

GET https://api.smartrecruiters.com/v1/companies/{company}/postings
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class SmartRecruitersProvider(BaseProvider):
    name = ATSProvider.SMARTRECRUITERS

    async def fetch(self, company: CompanyConfig) -> PollResult:
        token = company.board_token or company.slug
        etag = company.metadata.get("_etag")
        jobs: list[dict[str, Any]] = []
        offset = 0
        etag_out = None
        last_mod_out = None

        while True:
            url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
            data, status, headers = await self.get_json(
                url,
                etag=etag if offset == 0 else None,
                params={"offset": offset, "limit": 100, "q": "intern"},
            )
            if offset == 0:
                etag_out, last_mod_out = self.extract_cache_headers(headers)
                if status == 304:
                    return PollResult(
                        company=company.slug,
                        provider=self.name,
                        not_modified=True,
                        etag=etag_out or etag,
                        last_modified=last_mod_out,
                    )

            content = (data or {}).get("content", []) if isinstance(data, dict) else []
            jobs.extend(content)
            total = (data or {}).get("totalFound", len(jobs)) if isinstance(data, dict) else len(jobs)
            offset += len(content)
            if offset >= total or not content:
                break
            if offset > 2000:
                break

        internships = [self._normalize(company, job) for job in jobs]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
            etag=etag_out,
            last_modified=last_mod_out,
        )

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        loc = job.get("location") or {}
        location_parts = [
            loc.get("city"),
            loc.get("region"),
            loc.get("country"),
        ]
        location = ", ".join(p for p in location_parts if p)

        posted = None
        if job.get("releasedDate"):
            try:
                posted = datetime.fromisoformat(job["releasedDate"].replace("Z", "+00:00"))
            except ValueError:
                posted = None

        job_id = str(job.get("id") or job.get("uuid") or "")
        apply_url = (
            job.get("applyUrl")
            or f"https://jobs.smartrecruiters.com/{company.board_token or company.slug}/{job_id}"
        )

        return Internship(
            company=company.display_name,
            title=job.get("name") or job.get("title") or "Untitled",
            location=location or None,
            url=apply_url,
            job_id=job_id,
            provider=self.name,
            posted_date=posted,
            employment_type=(job.get("typeOfEmployment") or {}).get("label")
            if isinstance(job.get("typeOfEmployment"), dict)
            else None,
            remote=bool(loc.get("remote")) if isinstance(loc, dict) else None,
            description=job.get("jobAd", {}).get("sections", {})
            if isinstance(job.get("jobAd"), dict)
            else None,
            source="smartrecruiters",
            raw=job,
        )
