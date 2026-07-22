"""Configuration system — env vars + YAML company registry."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.models import ATSProvider, CompanyConfig, InternshipTerm


ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_to: str = ""

    # Paths
    database_path: str = "data/internships.db"
    companies_path: str = "companies/companies.yaml"
    log_level: str = "INFO"

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000
    enable_dashboard: bool = True
    enable_discovery: bool = True

    # Adaptive polling (seconds)
    poll_business_hours: int = 300
    poll_off_hours: int = 1200
    poll_hot: int = 120
    poll_inactive: int = 3600

    # Concurrency
    max_concurrent_polls: int = 50
    request_timeout_seconds: float = 25.0
    user_agent: str = (
        "InternshipIntelligence/0.1 (+https://github.com/local/internship-intelligence; research)"
    )

    # Filters
    target_terms: str = "Summer 2027,Fall 2026,Winter 2027,Spring 2027"
    min_notify_score: float = 40.0

    # Business hours (local wall clock, 24h)
    business_hour_start: int = 8
    business_hour_end: int = 20

    @property
    def database_path_abs(self) -> Path:
        p = Path(self.database_path)
        return p if p.is_absolute() else ROOT / p

    @property
    def companies_path_abs(self) -> Path:
        p = Path(self.companies_path)
        return p if p.is_absolute() else ROOT / p

    @property
    def target_term_list(self) -> list[InternshipTerm]:
        terms: list[InternshipTerm] = []
        for raw in self.target_terms.split(","):
            cleaned = raw.strip()
            for term in InternshipTerm:
                if term.value.lower() == cleaned.lower():
                    terms.append(term)
                    break
        return terms or [
            InternshipTerm.SUMMER_2027,
            InternshipTerm.FALL_2026,
            InternshipTerm.WINTER_2027,
            InternshipTerm.SPRING_2027,
        ]

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


# ---------------------------------------------------------------------------
# Title / description filter configuration
# ---------------------------------------------------------------------------

INCLUDE_PATTERNS: list[str] = [
    r"software\s*engineer[\s,/\-]*intern",
    r"software\s*engineering[\s,/\-]*intern",
    r"swe[\s,/\-]*intern",
    r"backend[\s,/\-]*intern",
    r"platform[\s,/\-]*intern",
    r"infrastructure[\s,/\-]*intern",
    r"distributed\s*systems[\s,/\-]*intern",
    r"ai\s*infrastructure[\s,/\-]*intern",
    r"ml\s*infrastructure[\s,/\-]*intern",
    r"systems[\s,/\-]*intern",
    r"security\s*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"full[\s-]*stack[\s,/\-]*intern",
    r"frontend[\s,/\-]*intern",
    r"front[\s-]*end[\s,/\-]*intern",
    r"machine\s*learning[\s,/\-]*intern",
    r"ml[\s,/\-]*intern",
    r"data\s*engineer(?:ing)?[\s,/\-]*intern",
    r"research\s*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"engineer(?:ing)?[\s,/\-]*intern",
    r"\bintern(?:ship)?\b.*(?:software|swe|backend|platform|infrastructure|systems)",
    r"(?:software|swe|backend|platform|infrastructure|systems).*\bintern",
]

EXCLUDE_PATTERNS: list[str] = [
    r"\bsenior\b",
    r"\bstaff\b",
    r"\bexperienced\b",
    r"\bprincipal\b",
    r"\bmanager\b",
    r"\bdirector\b",
    r"\bproduct\s+manager\b",
    r"\bqa\b",
    r"\bquality\s+assurance\b",
    r"\bmarketing\b",
    r"\bsales\b",
    r"\brecruiter\b",
    r"\bhr\s+intern\b",
    r"\bfinance\s+intern\b",
    r"\baccounting\s+intern\b",
    r"\blegal\s+intern\b",
    r"\bdesign\s+intern\b",
    r"\bux\s+intern\b",
    r"\bui\s+design",
]

# Ranking weights — higher = better match for target SWE internships
# [\s,/\-]* allows titles like "Software Engineer, Intern"
RANKING_RULES: list[dict[str, Any]] = [
    {"pattern": r"software\s*engineer(?:ing)?[\s,/\-]*intern", "score": 100},
    {"pattern": r"platform\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 98},
    {"pattern": r"infrastructure\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 97},
    {"pattern": r"backend\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 95},
    {"pattern": r"distributed\s*systems[\s,/\-]*intern", "score": 92},
    {"pattern": r"security\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 90},
    {"pattern": r"systems\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 90},
    {"pattern": r"ai\s*infrastructure[\s,/\-]*intern", "score": 92},
    {"pattern": r"ml\s*infrastructure[\s,/\-]*intern", "score": 92},
    {"pattern": r"swe[\s,/\-]*intern", "score": 100},
    {"pattern": r"full[\s-]*stack[\s,/\-]*intern", "score": 80},
    {"pattern": r"machine\s*learning[\s,/\-]*intern|ml[\s,/\-]*intern", "score": 85},
    {"pattern": r"data\s*engineer(?:ing)?[\s,/\-]*intern", "score": 75},
    {"pattern": r"frontend[\s,/\-]*intern|front[\s-]*end[\s,/\-]*intern", "score": 40},
    {"pattern": r"research\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 70},
    {"pattern": r"engineer(?:ing)?[\s,/\-]*intern", "score": 60},
]

TERM_PATTERNS: dict[InternshipTerm, list[str]] = {
    InternshipTerm.SUMMER_2027: [
        r"summer\s*2027",
        r"sum\s*['’]?27",
        r"2027\s*summer",
        r"s27",
    ],
    InternshipTerm.FALL_2026: [
        r"fall\s*2026",
        r"autumn\s*2026",
        r"f26",
        r"2026\s*fall",
    ],
    InternshipTerm.WINTER_2027: [
        r"winter\s*2027",
        r"w27",
        r"2027\s*winter",
        r"winter\s*['’]?27",
    ],
    InternshipTerm.SPRING_2027: [
        r"spring\s*2027",
        r"sp27",
        r"2027\s*spring",
        r"spring\s*['’]?27",
    ],
}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_companies(path: Path | None = None) -> list[CompanyConfig]:
    """Load companies.yaml into typed CompanyConfig list."""
    settings = get_settings()
    yaml_path = path or settings.companies_path_abs
    if not yaml_path.exists():
        return []

    with yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    companies_raw = data.get("companies", {})
    result: list[CompanyConfig] = []

    # Support both mapping and list formats
    if isinstance(companies_raw, dict):
        items = companies_raw.items()
    elif isinstance(companies_raw, list):
        items = ((c.get("slug", c.get("name", "")), c) for c in companies_raw)
    else:
        return []

    for slug, cfg in items:
        if not isinstance(cfg, dict):
            continue
        provider_raw = cfg.get("provider", "unknown")
        try:
            provider = ATSProvider(str(provider_raw).lower())
        except ValueError:
            provider = ATSProvider.UNKNOWN

        result.append(
            CompanyConfig(
                slug=str(slug),
                name=cfg.get("name"),
                provider=provider,
                board_token=cfg.get("board_token") or cfg.get("token") or str(slug),
                career_url=cfg.get("career_url") or cfg.get("url"),
                enabled=cfg.get("enabled", True),
                priority=int(cfg.get("priority", 0)),
                tags=list(cfg.get("tags", [])),
                metadata=dict(cfg.get("metadata", {})),
            )
        )
    return result


def save_companies(companies: list[CompanyConfig], path: Path | None = None) -> None:
    """Persist company registry back to YAML (used by discovery)."""
    settings = get_settings()
    yaml_path = path or settings.companies_path_abs
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {"companies": {}}
    for c in sorted(companies, key=lambda x: x.slug):
        entry: dict[str, Any] = {"provider": c.provider.value}
        if c.name:
            entry["name"] = c.name
        if c.board_token and c.board_token != c.slug:
            entry["board_token"] = c.board_token
        if c.career_url:
            entry["career_url"] = c.career_url
        if not c.enabled:
            entry["enabled"] = False
        if c.priority:
            entry["priority"] = c.priority
        if c.tags:
            entry["tags"] = c.tags
        if c.metadata:
            entry["metadata"] = c.metadata
        payload["companies"][c.slug] = entry

    with yaml_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=False)
