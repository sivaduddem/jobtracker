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

    # Adaptive polling (seconds) — keep as aggressive as polite API use allows
    poll_business_hours: int = 60
    poll_off_hours: int = 120
    poll_hot: int = 30
    poll_inactive: int = 300

    # Concurrency
    max_concurrent_polls: int = 50
    request_timeout_seconds: float = 25.0
    user_agent: str = (
        "InternshipIntelligence/0.1 (+https://github.com/local/internship-intelligence; research)"
    )

    # Filters
    target_terms: str = "Summer 2027,Fall 2026,Winter 2027,Spring 2027"
    min_notify_score: float = 40.0
    # Restrict to North America tech hubs: us_canada | any
    location_filter: str = "us_canada"

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
    # Core SWE / SDE
    r"software\s*engineer[\s,/\-]*intern",
    r"software\s*engineering[\s,/\-]*intern",
    r"software\s*development\s*engineer[\s,/\-]*intern",
    r"software\s*developer[\s,/\-]*intern",
    r"\bswe[\s,/\-]*intern",
    r"\bsde[\s,/\-]*intern",
    r"\bintern(?:ship)?\b.*\b(?:software|swe|sde)\b",
    r"\b(?:software|swe|sde)\b.*\bintern",
    # Product eng tracks
    r"backend[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"frontend[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"front[\s-]*end[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"full[\s-]*stack[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"platform[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"infrastructure[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"distributed\s*systems[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"site\s*reliability[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"\bsre[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"devops[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"security\s*(?:engineer(?:ing)?|software)?[\s,/\-]*intern",
    r"systems\s*software[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    r"software\s*systems[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern",
    # ML / AI / data (CS-track)
    r"machine\s*learning[\s,/\-]*(?:engineer(?:ing)?|research|scientist)?[\s,/\-]*intern",
    r"\bml[\s,/\-]*(?:engineer(?:ing)?|research|scientist)?[\s,/\-]*intern",
    r"\bai[\s,/\-]*(?:engineer(?:ing)?|software|research)?[\s,/\-]*intern",
    r"artificial\s*intelligence[\s,/\-]*intern",
    r"deep\s*learning[\s,/\-]*intern",
    r"computer\s*vision[\s,/\-]*intern",
    r"nlp[\s,/\-]*intern",
    r"data\s*engineer(?:ing)?[\s,/\-]*intern",
    r"ml\s*infrastructure[\s,/\-]*intern",
    r"ai\s*infrastructure[\s,/\-]*intern",
    # Embedded / firmware (CS/EE software track)
    r"embedded\s*(?:software|systems?|engineer(?:ing)?)?[\s,/\-]*intern",
    r"firmware[\s,/\-]*(?:engineer(?:ing)?|software)?[\s,/\-]*intern",
    r"\bintern(?:ship)?\b.*\b(?:embedded|firmware)\b",
    r"\b(?:embedded|firmware)\b.*\bintern",
    # Research eng when software/ML flavored
    r"research\s*(?:software\s*)?engineer(?:ing)?[\s,/\-]*intern",
    r"software\s*research[\s,/\-]*intern",
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
    # Non-CS engineering disciplines
    r"\bmechanical\b",
    r"\bmechatronic",
    r"\bcivil\b",
    r"\bchemical\b",
    r"\bindustrial\s+engineer",
    r"\bmanufacturing\s+engineer",
    r"\bprocess\s+engineer",
    r"\bstructural\b",
    r"\bthermal\b",
    r"\baerospace\s+engineer",
    r"\bbomedical\s+engineer",
    r"\bbioengineering\b",
    r"\benvironmental\s+engineer",
    r"\bpetroleum\b",
    r"\bnuclear\s+engineer",
    r"\bmaterials\s+engineer",
    r"\bhardware\s+engineer",
    r"\belectrical\s+engineer",
    r"\bfield\s+engineer",
    r"\bfacilit(?:y|ies)\s+engineer",
    r"\boptical\s+engineer",
    r"\brf\s+engineer",
    r"\banalog\b",
    r"\bmixed[\s-]*signal\b",
    r"\bpcb\b",
    r"\bvlsi\b",
    r"\bsilicon\s+design\b",
    r"\bphysical\s+design\b",
    r"\bsupply\s+chain\b",
    r"\boperations\s+intern\b",
    r"\bbusiness\s+intern\b",
    r"\bconsulting\s+intern\b",
]

# Ranking weights — higher = better match for target undergrad SWE internships
# [\s,/\-]* allows titles like "Software Engineer, Intern"
RANKING_RULES: list[dict[str, Any]] = [
    {"pattern": r"software\s*(?:development\s*)?engineer(?:ing)?[\s,/\-]*intern", "score": 100},
    {"pattern": r"\bswe[\s,/\-]*intern|\bsde[\s,/\-]*intern", "score": 100},
    {"pattern": r"software\s*developer[\s,/\-]*intern", "score": 98},
    {"pattern": r"platform\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 98},
    {"pattern": r"infrastructure\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 97},
    {"pattern": r"backend\s*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 95},
    {"pattern": r"embedded\s*(?:software|systems?|engineer(?:ing)?)?[\s,/\-]*intern", "score": 95},
    {"pattern": r"firmware[\s,/\-]*(?:engineer(?:ing)?|software)?[\s,/\-]*intern", "score": 95},
    {"pattern": r"distributed\s*systems[\s,/\-]*intern", "score": 92},
    {"pattern": r"ai\s*infrastructure[\s,/\-]*intern|ml\s*infrastructure[\s,/\-]*intern", "score": 92},
    {"pattern": r"security\s*(?:engineer(?:ing)?|software)?[\s,/\-]*intern", "score": 90},
    {"pattern": r"systems\s*software[\s,/\-]*intern|software\s*systems[\s,/\-]*intern", "score": 90},
    {"pattern": r"site\s*reliability[\s,/\-]*intern|\bsre[\s,/\-]*intern", "score": 88},
    {"pattern": r"machine\s*learning[\s,/\-]*intern|\bml[\s,/\-]*(?:engineer(?:ing)?)?[\s,/\-]*intern", "score": 90},
    {"pattern": r"\bai[\s,/\-]*(?:engineer(?:ing)?|software)?[\s,/\-]*intern|artificial\s*intelligence[\s,/\-]*intern", "score": 90},
    {"pattern": r"deep\s*learning[\s,/\-]*intern|computer\s*vision[\s,/\-]*intern", "score": 88},
    {"pattern": r"full[\s-]*stack[\s,/\-]*intern", "score": 80},
    {"pattern": r"data\s*engineer(?:ing)?[\s,/\-]*intern", "score": 75},
    {"pattern": r"research\s*(?:software\s*)?engineer(?:ing)?[\s,/\-]*intern", "score": 70},
    {"pattern": r"frontend[\s,/\-]*intern|front[\s-]*end[\s,/\-]*intern", "score": 40},
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
