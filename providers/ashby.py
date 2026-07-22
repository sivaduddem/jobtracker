"""Ashby job board API adapter.

Public API: https://api.ashbyhq.com/posting-api/job-board/{org}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class AshbyProvider(BaseProvider):
    name = ATSProvider.ASHBY

    def board_url(self, token: str) -> str:
        return f"https://api.ashbyhq.com/posting-api/job-board/{token}"

    async def fetch(self, company: CompanyConfig) -> PollResult:
        token = company.board_token or company.slug
        etag = company.metadata.get("_etag")
        url = self.board_url(token)

        data, status, headers = await self.get_json(
            url,
            etag=etag,
            last_modified=company.metadata.get("_last_modified"),
            params={"includeCompensation": "true"},
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

        jobs_raw = (data or {}).get("jobs", []) if isinstance(data, dict) else []
        internships = [self._normalize(company, job, token) for job in jobs_raw]

        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
            etag=etag_out,
            last_modified=last_mod_out,
        )

    def _normalize(
        self, company: CompanyConfig, job: dict[str, Any], token: str
    ) -> Internship:
        location = job.get("location")
        if isinstance(job.get("address"), dict):
            postal = job["address"].get("postalAddress")
            if postal:
                location = postal
        locations = job.get("locations") or []
        if not location and locations:
            names = []
            for loc in locations:
                if isinstance(loc, dict):
                    names.append(loc.get("name") or loc.get("location") or "")
                elif isinstance(loc, str):
                    names.append(loc)
            location = ", ".join(n for n in names if n)

        job_url = job.get("jobUrl") or job.get("applyUrl")
        if not job_url:
            job_id = job.get("id") or job.get("jobId")
            job_url = f"https://jobs.ashbyhq.com/{token}/{job_id}"

        posted = None
        for key in ("publishedAt", "updatedAt", "createdAt"):
            raw = job.get(key)
            if isinstance(raw, str):
                try:
                    posted = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    break
                except ValueError:
                    continue

        remote = job.get("isRemote")
        if remote is None and isinstance(location, str) and "remote" in location.lower():
            remote = True

        salary = None
        comp = job.get("compensation") or job.get("compensationTierSummary")
        if isinstance(comp, str):
            salary = comp
        elif isinstance(comp, dict):
            salary = comp.get("summary") or str(comp)

        return Internship(
            company=company.display_name,
            title=job.get("title") or "Untitled",
            location=location if isinstance(location, str) else None,
            url=job_url,
            job_id=str(job.get("id") or job.get("jobId") or ""),
            provider=self.name,
            posted_date=posted,
            employment_type=job.get("employmentType"),
            salary=salary,
            remote=remote,
            description=job.get("descriptionPlain") or job.get("descriptionHtml"),
            source="ashby",
            raw=job,
        )
