"""Oracle Cloud Recruiting adapter — HTML/JSON discovery."""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class OracleProvider(BaseProvider):
    name = ATSProvider.ORACLE

    async def fetch(self, company: CompanyConfig) -> PollResult:
        url = company.career_url or company.board_token
        if not url:
            return PollResult(
                company=company.slug,
                provider=self.name,
                error="Oracle requires career_url",
            )

        # Prefer candidate experience REST if present in metadata
        api = company.metadata.get("oracle_api")
        jobs: list[dict[str, Any]] = []
        if api:
            try:
                data, _, _ = await self.get_json(api, params={"keyword": "intern"})
                if isinstance(data, dict):
                    jobs = data.get("items") or data.get("jobs") or []
                elif isinstance(data, list):
                    jobs = data
            except Exception:
                jobs = []

        if not jobs:
            text, _, _ = await self.get_text(url)
            if text:
                jobs = self._parse_html(text, url)

        internships = [self._normalize(company, j) for j in jobs]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )

    def _parse_html(self, html: str, base: str) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a[href*='job'], a[href*='requisition']"):
            title = a.get_text(strip=True)
            if not title or "intern" not in title.lower():
                continue
            href = a.get("href", "")
            if href.startswith("/"):
                # Keep relative; company career host needed
                href = base.rstrip("/") + "/" + href.lstrip("/")
            jobs.append({"title": title, "url": href, "id": href})

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "JobPosting":
                    jobs.append(
                        {
                            "title": item.get("title"),
                            "url": item.get("url"),
                            "id": item.get("url") or item.get("title"),
                            "location": (item.get("jobLocation") or {}),
                            "description": item.get("description"),
                        }
                    )
        return jobs

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        loc = job.get("location")
        if isinstance(loc, dict):
            loc = loc.get("address", {}).get("addressLocality") if isinstance(loc.get("address"), dict) else str(loc)
        return Internship(
            company=company.display_name,
            title=job.get("title") or "Untitled",
            location=loc if isinstance(loc, str) else None,
            url=job.get("url") or company.career_url or "",
            job_id=str(job.get("id") or job.get("url") or job.get("title") or ""),
            provider=self.name,
            description=job.get("description"),
            source="oracle",
            raw=job,
        )
