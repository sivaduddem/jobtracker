"""Amazon Jobs adapter — official public search.json API.

GET https://www.amazon.jobs/en/search.json
  ?base_query=...&loc_query=...&result_limit=100&offset=0

No auth required. Respectful pagination with a hard page cap.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider

BASE = "https://www.amazon.jobs/en/search.json"
JOB_BASE = "https://www.amazon.jobs"


class AmazonProvider(BaseProvider):
    name = ATSProvider.AMAZON

    async def fetch(self, company: CompanyConfig) -> PollResult:
        queries = company.metadata.get("search_queries") or [
            "Software Development Engineer Internship",
            "Software Development Engineer Intern",
            "SDE Intern",
        ]
        locations = company.metadata.get("search_locations") or [
            "United States",
            "Canada",
        ]
        page_size = int(company.metadata.get("page_size") or 100)
        max_pages = int(company.metadata.get("max_pages") or 5)

        seen: dict[str, dict[str, Any]] = {}
        last_error: str | None = None

        for loc in locations:
            for query in queries:
                offset = 0
                for _ in range(max_pages):
                    url = (
                        f"{BASE}?base_query={quote_plus(str(query))}"
                        f"&loc_query={quote_plus(str(loc))}"
                        f"&result_limit={page_size}&offset={offset}"
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
                    for job in jobs:
                        job_id = str(
                            job.get("id")
                            or job.get("job_id")
                            or job.get("icims_id")
                            or ""
                        )
                        if not job_id or job_id in seen:
                            continue
                        title = (
                            job.get("title")
                            or job.get("job_title")
                            or ""
                        )
                        if "intern" not in title.lower():
                            continue
                        country = str(job.get("country_code") or "").upper()
                        if country and country not in {"US", "USA", "CA", "CAN"}:
                            continue
                        seen[job_id] = job
                    hits = int(data.get("hits") or 0)
                    offset += page_size
                    if offset >= hits or len(jobs) < page_size:
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
        job_id = str(job.get("id") or job.get("job_id") or job.get("icims_id") or "")
        path = job.get("job_path") or job.get("url_next_step") or ""
        if path and not str(path).startswith("http"):
            url = f"{JOB_BASE}{path}" if str(path).startswith("/") else f"{JOB_BASE}/{path}"
        else:
            url = str(path) if path else f"{JOB_BASE}/jobs/{job_id}"

        location = (
            job.get("normalized_location")
            or job.get("location")
            or job.get("city")
            or job.get("preferred_labor_market")
        )
        if isinstance(location, list):
            location = "; ".join(str(x) for x in location)

        return Internship(
            company=company.display_name,
            title=job.get("title") or job.get("job_title") or "Untitled",
            location=str(location) if location else None,
            url=url,
            job_id=job_id,
            provider=self.name,
            description=job.get("description") or job.get("basic_qualifications"),
            source="amazon",
            raw=job,
        )
