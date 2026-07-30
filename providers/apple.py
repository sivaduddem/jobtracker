"""Apple Jobs adapter — scrape official jobs.apple.com search HTML.

Apple's JSON search API is locked down (436), but the public search pages
embed role detail paths like /en-us/details/{id}/{slug}.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from core.models import ATSProvider, CompanyConfig, Internship, PollResult
from core.provider_base import BaseProvider

BASE = "https://jobs.apple.com/en-us/search"
DETAIL_RE = re.compile(
    r"(?:/en-us)?/details/(\d+)(?:/([a-z0-9-]+))?",
    re.IGNORECASE,
)
TITLE_NEAR_RE = re.compile(
    r"(Software Engineering[^\"<]{0,40}Intern[^\"<]{0,40}|Software Engineer[^\"<]{0,40}Intern[^\"<]{0,40})",
    re.IGNORECASE,
)
INTERN_RE = re.compile(r"\bintern(?:ship)?\b", re.IGNORECASE)


def _title_from_slug(slug: str) -> str:
    parts = slug.replace("---", " - ").split("-")
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.lower() in {"ios", "ai", "ml", "sre", "us", "uk", "phd", "bs", "ms"}:
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    return " ".join(out)


class AppleProvider(BaseProvider):
    name = ATSProvider.APPLE

    async def fetch(self, company: CompanyConfig) -> PollResult:
        queries = company.metadata.get("search_queries") or [
            "software engineer intern",
            "software engineering intern",
            "intern",
        ]
        # Apple location facet values from careers UI
        locations = company.metadata.get("search_locations") or [
            "united-states-USA",
        ]

        seen: dict[str, dict[str, Any]] = {}
        last_error: str | None = None

        for loc in locations:
            for query in queries:
                url = (
                    f"{BASE}?search={quote_plus(str(query))}"
                    f"&sort=relevance&location={quote_plus(str(loc))}"
                )
                try:
                    text, status, _ = await self.get_text(
                        url,
                        headers={
                            "Accept": "text/html,application/xhtml+xml",
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/122.0.0.0 Safari/537.36"
                            ),
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    continue
                if not text:
                    last_error = f"empty response ({status})"
                    continue

                for match in DETAIL_RE.finditer(text):
                    job_id = match.group(1)
                    slug = (match.group(2) or "").lower()
                    # Prefer slug signal; fall back to nearby title text
                    blob = slug
                    if not blob:
                        window = text[max(0, match.start() - 200) : match.end() + 200]
                        tm = TITLE_NEAR_RE.search(window)
                        if tm:
                            blob = tm.group(1).lower()
                            slug = re.sub(r"[^a-z0-9]+", "-", blob).strip("-")
                    if not INTERN_RE.search(blob.replace("-", " ")):
                        continue
                    if query == "intern" and not any(
                        t in blob
                        for t in (
                            "software",
                            "engineer",
                            "developer",
                            "machine-learning",
                            "ai-",
                            "sre",
                            "systems",
                        )
                    ):
                        continue
                    # Reject "internal" / "international" style false positives already
                    # handled by INTERN_RE word boundary on spaced blob.
                    if job_id in seen:
                        continue
                    loc_label = (
                        "United States"
                        if "united-states" in loc
                        else loc
                    )
                    title = _title_from_slug(slug) if slug else f"Apple Intern {job_id}"
                    seen[job_id] = {
                        "id": job_id,
                        "slug": slug or job_id,
                        "title": title,
                        "location": loc_label,
                        "url": (
                            f"https://jobs.apple.com/en-us/details/{job_id}/{slug}"
                            if slug
                            else f"https://jobs.apple.com/en-us/details/{job_id}"
                        ),
                    }

        if not seen and last_error:
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
                source="apple",
                raw=j,
            )
            for j in seen.values()
        ]
        return PollResult(
            company=company.slug,
            provider=self.name,
            total_jobs=len(internships),
            internships=internships,
        )
