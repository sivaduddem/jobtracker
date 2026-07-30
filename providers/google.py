"""Google Careers adapter (custom ATS — not Greenhouse/Lever/Ashby).

Google's public careers site embeds job result paths in HTML. We poll the
United States search pages for Software Engineering Intern roles and normalize
matches. No paid API required.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider

BASE = "https://www.google.com/about/careers/applications"
JOB_PATH_RE = re.compile(
    r"jobs/results/(\d+)-([a-z0-9-]+)",
    re.IGNORECASE,
)


def _title_from_slug(slug: str) -> str:
    """software-engineering-intern-bs-summer-2027 → readable title."""
    parts = slug.split("-")
    # Keep common tokens uppercase
    out: list[str] = []
    for p in parts:
        if p.lower() in {"bs", "ms", "phd", "usa", "sre", "ai", "ml"}:
            out.append(p.upper())
        elif p.isdigit():
            out.append(p)
        else:
            out.append(p.capitalize())
    # Insert commas before degree / term markers for readability
    title = " ".join(out)
    title = re.sub(r"\b(BS|MS|PHD)\b", r", \1,", title, flags=re.I)
    title = re.sub(r"\b(Summer|Fall|Winter|Spring)\b", r"\1", title)
    title = re.sub(r"\s+,", ",", title)
    title = re.sub(r",\s*,", ",", title)
    title = re.sub(r"\s{2,}", " ", title).strip(" ,")
    return title


class GoogleProvider(BaseProvider):
    name = ATSProvider.GOOGLE

    async def fetch(self, company: CompanyConfig) -> PollResult:
        queries = company.metadata.get("search_queries") or [
            "Software Engineering Intern",
            "Software Engineer Intern",
            "SWE Intern",
        ]
        locations = company.metadata.get("search_locations") or [
            "United States",
        ]

        jobs: dict[str, dict[str, Any]] = {}
        last_error: str | None = None

        for loc in locations:
            for q in queries:
                url = (
                    f"{BASE}/jobs/results"
                    f"?q={quote_plus(str(q))}"
                    f"&location={quote_plus(str(loc))}"
                )
                try:
                    text, status, _ = await self.get_text(url)
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    continue
                if not text:
                    last_error = f"empty response ({status})"
                    continue
                for job_id, slug in JOB_PATH_RE.findall(text):
                    slug_l = slug.lower()
                    if "intern" not in slug_l:
                        continue
                    # Prefer engineering-ish roles
                    if not any(
                        tok in slug_l
                        for tok in (
                            "software",
                            "engineer",
                            "swe",
                            "sre",
                            "site-reliability",
                        )
                    ):
                        continue
                    if job_id in jobs:
                        # Merge location labels across search queries
                        prev = jobs[job_id].get("location") or ""
                        if loc not in prev:
                            jobs[job_id]["location"] = (
                                f"{prev}; {loc}" if prev else loc
                            )
                        continue
                    jobs[job_id] = {
                        "id": job_id,
                        "slug": slug_l,
                        "title": _title_from_slug(slug_l),
                        "location": loc,
                        "url": f"{BASE}/jobs/results/{job_id}-{slug_l}",
                    }

        if not jobs and last_error:
            return PollResult(
                company=company.slug,
                provider=self.name,
                error=last_error,
            )

        internships = [
            Internship(
                company=company.display_name,
                title=j["title"],
                location=j["location"],
                url=j["url"],
                job_id=str(j["id"]),
                provider=self.name,
                remote=False,
                source="google",
                raw=j,
            )
            for j in jobs.values()
        ]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )
