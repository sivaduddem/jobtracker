"""Jobvite careers adapter — JSON feed when available, HTML fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class JobviteProvider(BaseProvider):
    name = ATSProvider.JOBVITE

    async def fetch(self, company: CompanyConfig) -> PollResult:
        token = company.board_token or company.slug
        # Jobvite often exposes a JSONP/JSON careers feed
        feed_url = f"https://jobs.jobvite.com/{token}/search?j=&c=&l="
        api_url = company.metadata.get("jobvite_api") or (
            f"https://jobs.jobvite.com/{token}/job"
        )

        jobs: list[dict[str, Any]] = []
        try:
            data, status, _ = await self.get_json(api_url)
            if isinstance(data, dict) and "positions" in data:
                jobs = data["positions"]
            elif isinstance(data, list):
                jobs = data
        except Exception:
            jobs = []

        if not jobs:
            # HTML scrape fallback
            text, status, _ = await self.get_text(feed_url)
            if text:
                jobs = self._parse_html(text, token)

        internships = [self._normalize(company, job, token) for job in jobs]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )

    def _parse_html(self, html: str, token: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[dict[str, Any]] = []
        for a in soup.select("a[href*='/job/']"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not title or "intern" not in title.lower():
                continue
            if href.startswith("/"):
                href = f"https://jobs.jobvite.com{href}"
            job_id = href.rstrip("/").split("/")[-1]
            loc_el = a.find_parent("tr") or a.find_parent("li") or a.parent
            location = loc_el.get_text(" ", strip=True) if loc_el else None
            jobs.append(
                {"title": title, "url": href, "id": job_id, "location": location}
            )

        # Some pages embed JSON in script tags
        for script in soup.find_all("script"):
            content = script.string or ""
            if "jobMap" in content or "positions" in content:
                m = re.search(r"(\{.*\"positions\".*\})", content, re.S)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        jobs.extend(data.get("positions", []))
                    except json.JSONDecodeError:
                        pass
        return jobs

    def _normalize(
        self, company: CompanyConfig, job: dict[str, Any], token: str
    ) -> Internship:
        job_id = str(job.get("id") or job.get("jobId") or job.get("requisitionId") or "")
        url = job.get("url") or job.get("applyUrl") or f"https://jobs.jobvite.com/{token}/job/{job_id}"
        return Internship(
            company=company.display_name,
            title=job.get("title") or job.get("jobTitle") or "Untitled",
            location=job.get("location") or job.get("jobLocation"),
            url=url,
            job_id=job_id or url,
            provider=self.name,
            description=job.get("description"),
            source="jobvite",
            raw=job,
        )
