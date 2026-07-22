"""Company discovery + ATS auto-classification."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import aiohttp

from core.config import load_companies, save_companies
from core.logging import get_logger
from core.models import ATSProvider, CompanyConfig, DiscoveryCandidate

log = get_logger("discovery")

# Fingerprints that reveal which ATS a careers page uses
ATS_FINGERPRINTS: list[tuple[ATSProvider, re.Pattern[str]]] = [
    (ATSProvider.GREENHOUSE, re.compile(r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.GREENHOUSE, re.compile(r"greenhouse\.io/embed/job_board/js\?for=([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.LEVER, re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.ASHBY, re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.ASHBY, re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.SMARTRECRUITERS, re.compile(r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.SMARTRECRUITERS, re.compile(r"api\.smartrecruiters\.com/v1/companies/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.JOBVITE, re.compile(r"jobs\.jobvite\.com/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.WORKDAY, re.compile(r"([a-zA-Z0-9_-]+)\.wd\d+\.myworkdayjobs\.com/([a-zA-Z0-9_-]+)", re.I)),
    (ATSProvider.ICIMS, re.compile(r"([a-zA-Z0-9_-]+)\.icims\.com", re.I)),
    (ATSProvider.SUCCESSFACTORS, re.compile(r"successfactors\.com|sap\.com.*career", re.I)),
    (ATSProvider.ORACLE, re.compile(r"oraclecloud\.com/.*/recruiting", re.I)),
    (ATSProvider.EIGHTFOLD, re.compile(r"eightfold\.ai", re.I)),
    (ATSProvider.TALEO, re.compile(r"taleo\.net", re.I)),
]


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


async def classify_ats(
    session: aiohttp.ClientSession,
    career_url: str,
    *,
    timeout: float = 15.0,
) -> tuple[ATSProvider | None, str | None, float]:
    """
    Fetch a careers page and detect ATS provider + board token.
    Returns (provider, board_token, confidence).
    """
    try:
        async with session.get(
            career_url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
            headers={"User-Agent": "InternshipIntelligence/0.1"},
        ) as resp:
            final_url = str(resp.url)
            text = await resp.text()
    except Exception as exc:  # noqa: BLE001
        log.debug("ATS classify failed for %s: %s", career_url, exc)
        return None, None, 0.0

    blob = f"{final_url}\n{text}"

    for provider, pattern in ATS_FINGERPRINTS:
        m = pattern.search(blob)
        if not m:
            continue
        token = m.group(1) if m.lastindex and m.lastindex >= 1 else None
        if provider == ATSProvider.WORKDAY and m.lastindex and m.lastindex >= 2:
            # Encode as "tenant:site"
            token = f"{m.group(1)}:{m.group(2)}"
        if provider in {
            ATSProvider.SUCCESSFACTORS,
            ATSProvider.ORACLE,
            ATSProvider.EIGHTFOLD,
            ATSProvider.TALEO,
        }:
            token = career_url
        return provider, token, 0.9

    return None, None, 0.0


async def probe_known_endpoints(
    session: aiohttp.ClientSession, slug: str
) -> tuple[ATSProvider | None, str | None, float]:
    """Try well-known public board URLs for a slug without a careers page."""
    probes: list[tuple[ATSProvider, str, str]] = [
        (ATSProvider.GREENHOUSE, slug, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
        (ATSProvider.LEVER, slug, f"https://api.lever.co/v0/postings/{slug}?mode=json"),
        (ATSProvider.ASHBY, slug, f"https://api.ashbyhq.com/posting-api/job-board/{slug}"),
        (
            ATSProvider.SMARTRECRUITERS,
            slug,
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
        ),
    ]
    for provider, token, url in probes:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "InternshipIntelligence/0.1", "Accept": "application/json"},
            ) as resp:
                if resp.status == 200:
                    return provider, token, 0.85
        except Exception:  # noqa: BLE001
            continue
    return None, None, 0.0


# ---- Discovery sources (lightweight, free, public) ----

async def discover_from_yc(session: aiohttp.ClientSession) -> list[DiscoveryCandidate]:
    """Pull recent YC companies from the public Algolia index (unofficial but free)."""
    candidates: list[DiscoveryCandidate] = []
    url = "https://yj4yk5bh2o-dsn.algolia.net/1/indexes/*/queries"
    # Public YC Algolia credentials are embedded in ycombinator.com front-end
    headers = {
        "X-Algolia-Application-Id": "YJ4YK5BH2O",
        "X-Algolia-API-Key": "8660bcc5a5560c318fc64498cef636bf",
        "Content-Type": "application/json",
    }
    body = {
        "requests": [
            {
                "indexName": "companies",
                "params": "query=&hitsPerPage=100&filters=batch:%22W26%22%20OR%20batch:%22S25%22%20OR%20batch:%22W25%22%20OR%20batch:%22S24%22",
            }
        ]
    }
    try:
        async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                log.warning("YC discovery HTTP %s", resp.status)
                return candidates
            data = await resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("YC discovery failed: %s", exc)
        return candidates

    hits = []
    for result in data.get("results", []):
        hits.extend(result.get("hits", []))

    for hit in hits:
        name = hit.get("name") or ""
        if not name:
            continue
        slug = slugify(hit.get("slug") or name)
        website = hit.get("website") or hit.get("url")
        candidates.append(
            DiscoveryCandidate(
                name=name,
                slug=slug,
                source="yc",
                website=website,
                career_url=(website.rstrip("/") + "/careers") if website else None,
                metadata={"batch": hit.get("batch"), "one_liner": hit.get("oneLiner")},
            )
        )
    log.info("YC discovery: %d candidates", len(candidates))
    return candidates


async def discover_from_github_intern_lists(
    session: aiohttp.ClientSession,
) -> list[DiscoveryCandidate]:
    """
    Parse well-known public internship list READMEs for company names.
    Uses raw.githubusercontent.com — free, no API key.
    """
    urls = [
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README.md",
    ]
    seen: set[str] = set()
    candidates: list[DiscoveryCandidate] = []
    # Markdown table rows often look like: | [Company](url) | ...
    row_re = re.compile(r"\|\s*\[([^\]]+)\]\(([^)]+)\)")

    for url in urls:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    continue
                text = await resp.text()
        except Exception:  # noqa: BLE001
            continue

        for m in row_re.finditer(text):
            name = m.group(1).strip()
            link = m.group(2).strip()
            if not name or name.lower() in {"company", "name"}:
                continue
            slug = slugify(name)
            if slug in seen:
                continue
            seen.add(slug)
            candidates.append(
                DiscoveryCandidate(
                    name=name,
                    slug=slug,
                    source="github-intern-list",
                    career_url=link if "http" in link else None,
                )
            )
    log.info("GitHub intern-list discovery: %d candidates", len(candidates))
    return candidates


SEED_TECH_COMPANIES: list[dict[str, Any]] = [
    {"name": "Stripe", "slug": "stripe", "provider": "greenhouse"},
    {"name": "Airbnb", "slug": "airbnb", "provider": "greenhouse"},
    {"name": "Databricks", "slug": "databricks", "provider": "greenhouse"},
    {"name": "Notion", "slug": "notion", "provider": "ashby"},
    {"name": "Discord", "slug": "discord", "provider": "greenhouse"},
    {"name": "Cloudflare", "slug": "cloudflare", "provider": "greenhouse"},
    {"name": "Figma", "slug": "figma", "provider": "greenhouse"},
    {"name": "OpenAI", "slug": "openai", "provider": "ashby"},
    {"name": "Cursor", "slug": "cursor", "provider": "ashby", "board_token": "cursor"},
    {"name": "Deepgram", "slug": "deepgram", "provider": "ashby"},
    {"name": "Scale AI", "slug": "scaleai", "provider": "greenhouse"},
    {"name": "Rippling", "slug": "rippling", "provider": "ashby"},
    {"name": "Brex", "slug": "brex", "provider": "greenhouse"},
    {"name": "Ramp", "slug": "ramp", "provider": "ashby"},
    {"name": "Shopify", "slug": "shopify", "provider": "greenhouse"},
    {"name": "Twilio", "slug": "twilio", "provider": "greenhouse"},
    {"name": "Dropbox", "slug": "dropbox", "provider": "greenhouse"},
    {"name": "Block", "slug": "squareup", "provider": "greenhouse"},
    {"name": "Coinbase", "slug": "coinbase", "provider": "greenhouse"},
    {"name": "Robinhood", "slug": "robinhood", "provider": "greenhouse"},
    {"name": "Affirm", "slug": "affirm", "provider": "greenhouse"},
    {"name": "DoorDash", "slug": "doordash", "provider": "greenhouse"},
    {"name": "Uber", "slug": "uber", "provider": "greenhouse"},
    {"name": "Lyft", "slug": "lyft", "provider": "greenhouse"},
    {"name": "Instacart", "slug": "instacart", "provider": "greenhouse"},
    {"name": "Snowflake", "slug": "snowflakecomputing", "provider": "greenhouse"},
    {"name": "Palantir", "slug": "palantir", "provider": "greenhouse"},
    {"name": "Anduril", "slug": "anduril", "provider": "ashby"},
    {"name": "Linear", "slug": "linear", "provider": "ashby"},
    {"name": "Datadog", "slug": "datadog", "provider": "greenhouse"},
    {"name": "MongoDB", "slug": "mongodb", "provider": "greenhouse"},
    {"name": "Elastic", "slug": "elastic", "provider": "greenhouse"},
    {"name": "HashiCorp", "slug": "hashicorp", "provider": "greenhouse"},
    {"name": "GitLab", "slug": "gitlab", "provider": "greenhouse"},
    {"name": "Asana", "slug": "asana", "provider": "greenhouse"},
    {"name": "Airtable", "slug": "airtable", "provider": "ashby"},
    {"name": "Canva", "slug": "canva", "provider": "greenhouse"},
    {"name": "Grammarly", "slug": "grammarly", "provider": "greenhouse"},
    {"name": "Duolingo", "slug": "duolingo", "provider": "greenhouse"},
    {"name": "Roblox", "slug": "roblox", "provider": "greenhouse"},
    {"name": "Spotify", "slug": "spotify", "provider": "lever"},
    {"name": "Twitch", "slug": "twitch", "provider": "greenhouse"},
    {"name": "Reddit", "slug": "reddit", "provider": "greenhouse"},
]


class DiscoveryEngine:
    """Discover companies, classify ATS, merge into companies.yaml."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def run(self, *, classify: bool = True, limit: int | None = None) -> int:
        existing = {c.slug: c for c in load_companies()}
        candidates: list[DiscoveryCandidate] = []

        # Always ensure seed tech companies exist
        for seed in SEED_TECH_COMPANIES:
            candidates.append(
                DiscoveryCandidate(
                    name=seed["name"],
                    slug=seed["slug"],
                    source="seed",
                    provider=ATSProvider(seed["provider"]),
                    board_token=seed.get("board_token", seed["slug"]),
                    confidence=1.0,
                )
            )

        candidates.extend(await discover_from_yc(self.session))
        candidates.extend(await discover_from_github_intern_lists(self.session))

        if limit:
            candidates = candidates[:limit]

        added = 0
        for cand in candidates:
            if cand.slug in existing:
                continue

            provider = cand.provider
            token = cand.board_token
            confidence = cand.confidence

            if classify and provider is None:
                if cand.career_url:
                    provider, token, confidence = await classify_ats(
                        self.session, cand.career_url
                    )
                if provider is None:
                    provider, token, confidence = await probe_known_endpoints(
                        self.session, cand.slug
                    )

            if provider is None or provider == ATSProvider.UNKNOWN:
                log.debug("Skipping %s — ATS unknown", cand.name)
                continue

            cfg = CompanyConfig(
                slug=cand.slug,
                name=cand.name,
                provider=provider,
                board_token=token or cand.slug,
                career_url=cand.career_url,
                tags=[cand.source],
                metadata={"discovery_confidence": confidence, **cand.metadata},
            )
            existing[cand.slug] = cfg
            added += 1
            log.info(
                "Discovered %s → %s (%s)",
                cand.name,
                provider.value,
                token or cand.slug,
            )

        if added:
            save_companies(list(existing.values()))
            log.info("Added %d companies to registry", added)
        return added
