"""Core data models for the Internship Intelligence Platform."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, computed_field


class ATSProvider(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    SMARTRECRUITERS = "smartrecruiters"
    ICIMS = "icims"
    SUCCESSFACTORS = "successfactors"
    ORACLE = "oracle"
    JOBVITE = "jobvite"
    EIGHTFOLD = "eightfold"
    TALEO = "taleo"
    GOOGLE = "google"
    UNKNOWN = "unknown"


class InternshipTerm(StrEnum):
    SUMMER_2027 = "Summer 2027"
    FALL_2026 = "Fall 2026"
    WINTER_2027 = "Winter 2027"
    SPRING_2027 = "Spring 2027"
    UNKNOWN = "Unknown"


class ApplicationStatus(StrEnum):
    SAVED = "saved"
    APPLIED = "applied"
    OA = "oa"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class CompanyConfig(BaseModel):
    """YAML-backed company monitoring configuration."""

    slug: str
    name: str | None = None
    provider: ATSProvider
    board_token: str | None = None  # Greenhouse board token, Lever site, Ashby org, etc.
    career_url: str | None = None
    enabled: bool = True
    priority: int = 0  # Higher = poll more often
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name or self.slug.replace("-", " ").replace("_", " ").title()


class Internship(BaseModel):
    """Normalized internship posting across all ATS providers."""

    company: str
    title: str
    location: str | None = None
    url: str
    job_id: str
    provider: ATSProvider
    term: InternshipTerm = InternshipTerm.UNKNOWN
    posted_date: datetime | None = None
    employment_type: str | None = None
    salary: str | None = None
    remote: bool | None = None
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    description: str | None = None
    source: str = "ats"
    score: float = 0.0
    is_active: bool = True
    # Stable config key (e.g. "stripe"); company holds display name for UI/alerts
    company_slug: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url_hash(self) -> str:
        return sha256(self.url.strip().lower().encode()).hexdigest()[:32]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dedupe_key(self) -> str:
        """Stable identity across re-scrapes: provider + company + job_id."""
        base = f"{self.provider.value}:{self.company.lower()}:{self.job_id}"
        return sha256(base.encode()).hexdigest()[:32]


class PollResult(BaseModel):
    """Outcome of a single company poll cycle."""

    company: str
    provider: ATSProvider
    total_jobs: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0
    removed_jobs: int = 0
    internships: list[Internship] = Field(default_factory=list)
    error: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    duration_ms: float = 0.0
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyState(BaseModel):
    """Runtime polling state for a company."""

    slug: str
    provider: ATSProvider
    etag: str | None = None
    last_modified: str | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    consecutive_errors: int = 0
    poll_interval_seconds: int = 300
    next_poll_at: datetime | None = None
    jobs_found_total: int = 0
    active_jobs: int = 0
    recent_activity: bool = False
    predicted_hot: bool = False


class NotificationPayload(BaseModel):
    """Channel-agnostic notification payload."""

    internship: Internship
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)


class DiscoveryCandidate(BaseModel):
    """A company discovered from an external source, pending ATS classification."""

    name: str
    slug: str
    source: str
    career_url: str | None = None
    website: str | None = None
    provider: ATSProvider | None = None
    board_token: str | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class HistoricalOpening(BaseModel):
    """Past internship opening date for prediction."""

    company: str
    year: int
    opened_on: datetime
    term: InternshipTerm | None = None
    title: str | None = None


class ApplicationRecord(BaseModel):
    """Optional application tracker entry."""

    dedupe_key: str
    status: ApplicationStatus = ApplicationStatus.SAVED
    resume_version: str | None = None
    notes: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
