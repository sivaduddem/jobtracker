"""Meta Careers adapter — public GraphQL used by metacareers.com/jobsearch/.

POST https://www.metacareers.com/graphql
  RelayModern query: CareersJobSearchResultsDataQuery

Meta may return HTTP 400 from some networks/bot filters. When reachable,
this returns internship / university-grad engineering roles.
"""

from __future__ import annotations

import json
import re
from typing import Any

import aiohttp

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider

API = "https://www.metacareers.com/graphql"
JOB_BASE = "https://www.metacareers.com/jobs"
INTERN_RE = re.compile(r"\bintern(?:ship)?\b", re.IGNORECASE)

# Default Relay doc_id used by the public careers frontend / community scrapers.
# Overridable via company.metadata.doc_id if Meta rotates it.
DEFAULT_DOC_ID = "29615178951461218"
DEFAULT_TEAMS = [
    "Internship - Engineering, Tech & Design",
    "University Grad - Engineering, Tech & Design",
]


class MetaProvider(BaseProvider):
    name = ATSProvider.META

    async def fetch(self, company: CompanyConfig) -> PollResult:
        queries = company.metadata.get("search_queries")
        # None query = team-scoped listing (Meta's own internship buckets)
        if queries is None:
            queries = [None, "Software Engineer Intern", "Software Engineering Intern"]
        teams = company.metadata.get("teams") or DEFAULT_TEAMS
        doc_id = str(company.metadata.get("doc_id") or DEFAULT_DOC_ID)
        lsd = str(company.metadata.get("lsd") or "AdFL9XlD5sA")
        asbd = str(company.metadata.get("asbd_id") or "359341")

        seen: dict[str, dict[str, Any]] = {}
        last_error: str | None = None

        for query in queries:
            try:
                jobs = await self._search(
                    teams=list(teams),
                    query=query,
                    doc_id=doc_id,
                    lsd=lsd,
                    asbd=asbd,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue

            for job in jobs:
                title = job.get("title") or ""
                title_l = title.lower()
                is_intern = bool(INTERN_RE.search(title))
                is_eng = any(
                    t in title_l
                    for t in (
                        "software",
                        "engineer",
                        "swe",
                        "research",
                        "machine learning",
                        "infrastructure",
                        "security",
                        "data engineer",
                        "sre",
                    )
                )
                if not is_eng:
                    continue
                if is_intern:
                    pass
                elif company.metadata.get("include_university_grad", False):
                    pass
                else:
                    continue

                job_id = str(job.get("id") or "")
                if not job_id or job_id in seen:
                    continue
                seen[job_id] = job

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

    async def _search(
        self,
        *,
        teams: list[str],
        query: str | None,
        doc_id: str,
        lsd: str,
        asbd: str,
    ) -> list[dict[str, Any]]:
        variables = {
            "search_input": {
                "q": query,
                "divisions": [],
                "offices": [],
                "roles": [],
                "leadership_levels": [],
                "saved_jobs": [],
                "saved_searches": [],
                "sub_teams": [],
                "teams": teams,
                "is_leadership": False,
                "is_remote_only": False,
                "sort_by_new": True,
                "results_per_page": None,
            }
        }
        form = {
            "lsd": lsd,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": "CareersJobSearchResultsDataQuery",
            "variables": json.dumps(variables),
            "doc_id": doc_id,
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "Origin": "https://www.metacareers.com",
            "Referer": "https://www.metacareers.com/jobsearch/",
            "x-asbd-id": asbd,
            "x-fb-friendly-name": "CareersJobSearchResultsDataQuery",
            "x-fb-lsd": lsd,
        }
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        async with self.session.post(
            API, data=form, headers=headers, timeout=timeout
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"Meta GraphQL HTTP {resp.status}: {text[:180]}",
                    headers=resp.headers,
                )
            payload = json.loads(text)

        if not isinstance(payload, dict):
            return []
        if payload.get("errors"):
            raise RuntimeError(f"Meta GraphQL errors: {payload['errors']!r}"[:400])
        jobs = (
            payload.get("data", {})
            .get("job_search_with_featured_jobs", {})
            .get("all_jobs")
            or []
        )
        return [j for j in jobs if isinstance(j, dict)]

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        job_id = str(job.get("id") or "")
        locs = job.get("locations") or []
        if isinstance(locs, list):
            location = "; ".join(str(x) for x in locs if x)
        else:
            location = str(locs) if locs else None
        return Internship(
            company=company.display_name,
            title=job.get("title") or "Untitled",
            location=location,
            url=f"{JOB_BASE}/{job_id}" if job_id else company.career_url or JOB_BASE,
            job_id=job_id,
            provider=self.name,
            source="meta",
            raw=job,
        )
