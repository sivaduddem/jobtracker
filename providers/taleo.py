"""Oracle Taleo adapter — HTML + JSON-LD discovery."""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class TaleoProvider(BaseProvider):
    name = ATSProvider.TALEO

    async def fetch(self, company: CompanyConfig) -> PollResult:
        url = company.career_url or company.board_token
        if not url:
            return PollResult(
                company=company.slug,
                provider=self.name,
                error="Taleo requires career_url",
            )

        text, _, _ = await self.get_text(url)
        jobs = self._parse(text or "") if text else []
        internships = [self._normalize(company, j) for j in jobs]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )

    def _parse(self, html: str) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "JobPosting":
                    title = item.get("title") or ""
                    if "intern" not in title.lower():
                        continue
                    jobs.append(
                        {
                            "title": title,
                            "url": item.get("url"),
                            "id": item.get("url") or title,
                            "description": item.get("description"),
                        }
                    )
        for a in soup.select("a"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if title and "intern" in title.lower() and href:
                jobs.append({"title": title, "url": href, "id": href})
        return jobs

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        return Internship(
            company=company.display_name,
            title=job.get("title") or "Untitled",
            location=job.get("location"),
            url=job.get("url") or "",
            job_id=str(job.get("id") or ""),
            provider=self.name,
            description=job.get("description"),
            source="taleo",
            raw=job,
        )
