"""Eightfold AI careers adapter."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider


class EightfoldProvider(BaseProvider):
    name = ATSProvider.EIGHTFOLD

    async def fetch(self, company: CompanyConfig) -> PollResult:
        url = company.career_url or company.board_token
        if not url:
            return PollResult(
                company=company.slug,
                provider=self.name,
                error="Eightfold requires career_url",
            )

        # Eightfold often exposes /api/apply/v2/jobs
        api = company.metadata.get("eightfold_api")
        jobs: list[dict[str, Any]] = []
        if api:
            try:
                data, _, _ = await self.get_json(api, params={"domain": company.slug, "query": "intern"})
                if isinstance(data, dict):
                    jobs = data.get("data", {}).get("positions") or data.get("positions") or []
            except Exception:
                pass

        if not jobs:
            text, _, _ = await self.get_text(url)
            if text:
                jobs = self._parse(text)

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
        for script in soup.find_all("script"):
            content = script.string or ""
            if "positions" in content and "{" in content:
                m = re.search(r"(\{.*\"positions\".*\})", content, re.S)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        jobs.extend(data.get("positions", []))
                    except json.JSONDecodeError:
                        pass
        for a in soup.select("a[href*='position'], a[href*='job']"):
            title = a.get_text(strip=True)
            if title and "intern" in title.lower():
                jobs.append({"name": title, "canonicalPositionUrl": a.get("href"), "id": a.get("href")})
        return jobs

    def _normalize(self, company: CompanyConfig, job: dict[str, Any]) -> Internship:
        return Internship(
            company=company.display_name,
            title=job.get("name") or job.get("title") or "Untitled",
            location=job.get("location") or job.get("locations"),
            url=job.get("canonicalPositionUrl") or job.get("url") or "",
            job_id=str(job.get("id") or job.get("positionId") or ""),
            provider=self.name,
            description=job.get("jobDescription"),
            source="eightfold",
            raw=job,
        )
