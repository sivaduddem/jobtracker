"""AMD Careers adapter — official careers.amd.com JSON API (Phenom/Jibe).

GET https://careers.amd.com/api/jobs
  ?keywords=...&limit=20&page=1&sortBy=relevance&descending=false&internal=false
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider

API = "https://careers.amd.com/api/jobs"
JOB_BASE = "https://careers.amd.com/careers-home/jobs"


class AMDProvider(BaseProvider):
    name = ATSProvider.AMD

    async def fetch(self, company: CompanyConfig) -> PollResult:
        queries = company.metadata.get("search_queries") or [
            "Software Engineer Intern",
            "Software Development Intern",
            "intern",
        ]
        page_size = int(company.metadata.get("page_size") or 20)
        max_pages = int(company.metadata.get("max_pages") or 5)
        api = company.metadata.get("api_url") or API
        job_base = company.metadata.get("job_base") or JOB_BASE

        seen: dict[str, dict[str, Any]] = {}
        last_error: str | None = None

        for query in queries:
            for page in range(1, max_pages + 1):
                url = (
                    f"{api}?keywords={quote_plus(str(query))}"
                    f"&limit={page_size}&page={page}"
                    f"&sortBy=relevance&descending=false&internal=false"
                )
                try:
                    data, status, _ = await self.get_json(
                        url,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": self.settings.user_agent,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    break
                if not isinstance(data, dict):
                    last_error = f"unexpected response ({status})"
                    break
                jobs = data.get("jobs") or []
                if not jobs:
                    break
                for raw in jobs:
                    job = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
                    if not isinstance(job, dict):
                        continue
                    title = job.get("title") or ""
                    if "intern" not in title.lower():
                        continue
                    # Prefer software/engineering roles when query is broad
                    title_l = title.lower()
                    if query == "intern" and not any(
                        t in title_l
                        for t in ("software", "engineer", "developer", "firmware", "systems")
                    ):
                        continue
                    job_id = str(job.get("req_id") or job.get("slug") or job.get("id") or "")
                    if not job_id or job_id in seen:
                        continue
                    seen[job_id] = job

                total = int(
                    data.get("totalCount")
                    or data.get("count")
                    or data.get("total")
                    or 0
                )
                if total and page * page_size >= total:
                    break
                if len(jobs) < page_size:
                    break

        if not seen and last_error:
            return PollResult(
                company=company.slug,
                provider=self.name,
                error=last_error,
            )

        internships = [
            self._normalize(company, j, job_base) for j in seen.values()
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
        job_base: str,
    ) -> Internship:
        job_id = str(job.get("req_id") or job.get("slug") or job.get("id") or "")
        slug = job.get("slug") or job_id
        url = job.get("apply_url") or job.get("meta_data", {}).get("canonical_url")
        if not url:
            url = f"{job_base}/{slug}" if slug else job_base

        loc = job.get("locations") or job.get("location") or job.get("city")
        if isinstance(loc, list):
            parts: list[str] = []
            for item in loc:
                if isinstance(item, dict):
                    parts.append(
                        item.get("name")
                        or item.get("city")
                        or item.get("location")
                        or str(item)
                    )
                else:
                    parts.append(str(item))
            location = "; ".join(p for p in parts if p)
        elif isinstance(loc, dict):
            location = loc.get("name") or loc.get("city") or str(loc)
        else:
            location = str(loc) if loc else None

        return Internship(
            company=company.display_name,
            title=job.get("title") or "Untitled",
            location=location,
            url=str(url),
            job_id=job_id,
            provider=self.name,
            description=job.get("description"),
            source="amd",
            raw=job,
        )
