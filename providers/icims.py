"""iCIMS careers adapter — HTML/JSON discovery with light parsing."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class ICIMSProvider(BaseProvider):
    name = ATSProvider.ICIMS

    async def fetch(self, company: CompanyConfig) -> PollResult:
        token = company.board_token or company.slug
        base = company.career_url or f"https://careers-{token}.icims.com"
        # iCIMS search endpoint (varies); try common patterns
        search_urls = [
            f"{base.rstrip('/')}/jobs/search?ss=1&searchKeyword=intern",
            f"https://{token}.icims.com/jobs/search?ss=1&searchKeyword=intern",
            f"https://careers-{token}.icims.com/jobs/search?ss=1&searchKeyword=intern",
        ]

        jobs: list[dict[str, Any]] = []
        last_error = None
        for url in search_urls:
            try:
                text, status, _ = await self.get_text(url)
                if not text:
                    continue
                parsed = self._parse(text, url)
                if parsed:
                    jobs = parsed
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue

        if not jobs and last_error:
            return PollResult(company=company.slug, provider=self.name, error=last_error)

        internships = [self._normalize(company, j) for j in jobs]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )

    def _parse(self, html: str, base_url: str) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        # Embedded JSON
        for m in re.finditer(r"(\{[^{}]*\"jobTitle\"[^{}]*\})", html):
            try:
                jobs.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass

        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a[href*='/jobs/']"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not title or len(title) < 3:
                continue
            if "intern" not in title.lower() and "intern" not in href.lower():
                continue
            full = urljoin(base_url, href)
            job_id = re.search(r"/jobs/(\d+)", full)
            jobs.append(
                {
                    "title": title,
                    "url": full,
                    "id": job_id.group(1) if job_id else full,
                }
            )
        return jobs

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        return Internship(
            company=company.display_name,
            title=job.get("title") or job.get("jobTitle") or "Untitled",
            location=job.get("location"),
            url=job.get("url") or "",
            job_id=str(job.get("id") or job.get("url") or ""),
            provider=self.name,
            description=job.get("description"),
            source="icims",
            raw=job,
        )
