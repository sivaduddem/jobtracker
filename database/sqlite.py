"""SQLite persistence — jobs, company state, history, applications."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from core.logging import get_logger
from core.models import (
    ApplicationRecord,
    ApplicationStatus,
    ATSProvider,
    CompanyState,
    HistoricalOpening,
    Internship,
    InternshipTerm,
)

log = get_logger("storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS internships (
    dedupe_key TEXT PRIMARY KEY,
    url_hash TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    url TEXT NOT NULL,
    job_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    term TEXT,
    posted_date TEXT,
    employment_type TEXT,
    salary TEXT,
    remote INTEGER,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    description TEXT,
    source TEXT,
    score REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    raw_json TEXT,
    notified INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_internships_company ON internships(company);
CREATE INDEX IF NOT EXISTS idx_internships_active ON internships(is_active);
CREATE INDEX IF NOT EXISTS idx_internships_score ON internships(score DESC);
CREATE INDEX IF NOT EXISTS idx_internships_first_seen ON internships(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_internships_url_hash ON internships(url_hash);

CREATE TABLE IF NOT EXISTS company_state (
    slug TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    last_success TEXT,
    last_error TEXT,
    consecutive_errors INTEGER DEFAULT 0,
    poll_interval_seconds INTEGER DEFAULT 300,
    next_poll_at TEXT,
    jobs_found_total INTEGER DEFAULT 0,
    active_jobs INTEGER DEFAULT 0,
    recent_activity INTEGER DEFAULT 0,
    predicted_hot INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS poll_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    provider TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    total_jobs INTEGER,
    new_jobs INTEGER,
    error TEXT,
    duration_ms REAL,
    not_modified INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_poll_log_checked ON poll_log(checked_at DESC);

CREATE TABLE IF NOT EXISTS historical_openings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    year INTEGER NOT NULL,
    opened_on TEXT NOT NULL,
    term TEXT,
    title TEXT,
    UNIQUE(company, year, opened_on, title)
);

CREATE TABLE IF NOT EXISTS applications (
    dedupe_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    resume_version TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        log.info("SQLite ready at %s", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage not connected")
        return self._db

    # ----- Internships -----

    async def known_keys(self) -> set[str]:
        keys: set[str] = set()
        async with self.db.execute(
            "SELECT dedupe_key, url_hash FROM internships"
        ) as cur:
            async for row in cur:
                keys.add(row["dedupe_key"])
                keys.add(row["url_hash"])
        return keys

    async def upsert_internship(
        self,
        internship: Internship,
        *,
        notify: bool = False,
        company_slug: str | None = None,
    ) -> tuple[bool, bool]:
        """
        Insert or update. Returns (is_new, should_notify).
        should_notify is True only for brand-new rows that haven't been notified.

        company_slug: stable companies.yaml key used for historical prediction.
        """
        if company_slug:
            internship.company_slug = company_slug
        now = datetime.utcnow().isoformat()
        existing = await self.get_by_dedupe(internship.dedupe_key)
        if existing is None:
            # Also check url_hash collision (same posting, different job_id encoding)
            async with self.db.execute(
                "SELECT * FROM internships WHERE url_hash = ?",
                (internship.url_hash,),
            ) as cur:
                by_url = await cur.fetchone()
            if by_url:
                await self.db.execute(
                    """
                    UPDATE internships SET last_seen = ?, is_active = 1,
                           title = ?, location = ?, score = ?, description = ?
                    WHERE url_hash = ?
                    """,
                    (
                        now,
                        internship.title,
                        internship.location,
                        internship.score,
                        internship.description,
                        internship.url_hash,
                    ),
                )
                await self.db.commit()
                return False, False

            await self.db.execute(
                """
                INSERT INTO internships (
                    dedupe_key, url_hash, company, title, location, url, job_id,
                    provider, term, posted_date, employment_type, salary, remote,
                    first_seen, last_seen, description, source, score, is_active,
                    raw_json, notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    internship.dedupe_key,
                    internship.url_hash,
                    internship.company,
                    internship.title,
                    internship.location,
                    internship.url,
                    internship.job_id,
                    internship.provider.value,
                    internship.term.value,
                    _dt(internship.posted_date),
                    internship.employment_type,
                    internship.salary,
                    1 if internship.remote else (0 if internship.remote is False else None),
                    _dt(internship.first_seen) or now,
                    now,
                    internship.description,
                    internship.source,
                    internship.score,
                    json.dumps(internship.raw) if internship.raw else None,
                    1 if notify else 0,
                ),
            )
            await self.db.commit()
            # Record historical opening for prediction (prefer stable slug)
            await self.record_historical_opening(
                internship, company_slug=internship.company_slug
            )
            return True, notify

        await self.db.execute(
            """
            UPDATE internships SET last_seen = ?, is_active = 1,
                   title = ?, location = ?, score = ?, description = ?,
                   term = COALESCE(?, term)
            WHERE dedupe_key = ?
            """,
            (
                now,
                internship.title,
                internship.location,
                internship.score,
                internship.description,
                internship.term.value if internship.term != InternshipTerm.UNKNOWN else None,
                internship.dedupe_key,
            ),
        )
        await self.db.commit()
        return False, False

    async def mark_notified(self, dedupe_key: str) -> None:
        await self.db.execute(
            "UPDATE internships SET notified = 1 WHERE dedupe_key = ?",
            (dedupe_key,),
        )
        await self.db.commit()

    async def get_by_dedupe(self, dedupe_key: str) -> Internship | None:
        async with self.db.execute(
            "SELECT * FROM internships WHERE dedupe_key = ?", (dedupe_key,)
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_internship(row) if row else None

    async def mark_missing_inactive(
        self, company: str, provider: ATSProvider, seen_job_ids: set[str]
    ) -> int:
        """Mark jobs for this company as inactive if not in the latest scrape."""
        async with self.db.execute(
            "SELECT dedupe_key, job_id FROM internships WHERE company = ? AND provider = ? AND is_active = 1",
            (company, provider.value),
        ) as cur:
            rows = await cur.fetchall()

        removed = 0
        now = datetime.utcnow().isoformat()
        for row in rows:
            if row["job_id"] not in seen_job_ids:
                await self.db.execute(
                    "UPDATE internships SET is_active = 0, last_seen = ? WHERE dedupe_key = ?",
                    (now, row["dedupe_key"]),
                )
                removed += 1
        if removed:
            await self.db.commit()
        return removed

    async def list_internships(
        self,
        *,
        active_only: bool = True,
        company: str | None = None,
        search: str | None = None,
        min_score: float | None = None,
        limit: int = 100,
        offset: int = 0,
        sort: str = "first_seen",
        descending: bool = True,
    ) -> list[Internship]:
        allowed_sort = {
            "first_seen",
            "last_seen",
            "score",
            "company",
            "title",
        }
        sort_col = sort if sort in allowed_sort else "first_seen"
        direction = "DESC" if descending else "ASC"
        clauses = []
        params: list[Any] = []
        if active_only:
            clauses.append("is_active = 1")
        if company:
            clauses.append("company = ?")
            params.append(company)
        if search:
            clauses.append("(title LIKE ? OR company LIKE ? OR location LIKE ?)")
            q = f"%{search}%"
            params.extend([q, q, q])
        if min_score is not None:
            clauses.append("score >= ?")
            params.append(min_score)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM internships{where} ORDER BY {sort_col} {direction} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with self.db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_internship(r) for r in rows]

    async def count_internships(self, *, active_only: bool = True) -> int:
        sql = "SELECT COUNT(*) AS c FROM internships"
        if active_only:
            sql += " WHERE is_active = 1"
        async with self.db.execute(sql) as cur:
            row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def stats(self) -> dict[str, Any]:
        active = await self.count_internships(active_only=True)
        total = await self.count_internships(active_only=False)
        async with self.db.execute(
            "SELECT COUNT(*) AS c FROM internships WHERE is_active = 0"
        ) as cur:
            removed = int((await cur.fetchone())["c"])
        async with self.db.execute("SELECT COUNT(*) AS c FROM company_state") as cur:
            companies = int((await cur.fetchone())["c"])
        async with self.db.execute(
            "SELECT COUNT(*) AS c FROM company_state WHERE last_error IS NOT NULL AND consecutive_errors > 0"
        ) as cur:
            errors = int((await cur.fetchone())["c"])
        async with self.db.execute(
            "SELECT MAX(last_success) AS m FROM company_state"
        ) as cur:
            last_success = (await cur.fetchone())["m"]
        return {
            "companies_monitored": companies,
            "jobs_active": active,
            "jobs_total": total,
            "jobs_removed": removed,
            "companies_with_errors": errors,
            "last_successful_scrape": last_success,
        }

    # ----- Company state -----

    async def get_company_state(self, slug: str) -> CompanyState | None:
        async with self.db.execute(
            "SELECT * FROM company_state WHERE slug = ?", (slug,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return CompanyState(
            slug=row["slug"],
            provider=ATSProvider(row["provider"]),
            etag=row["etag"],
            last_modified=row["last_modified"],
            last_success=_parse_dt(row["last_success"]),
            last_error=row["last_error"],
            consecutive_errors=row["consecutive_errors"] or 0,
            poll_interval_seconds=row["poll_interval_seconds"] or 300,
            next_poll_at=_parse_dt(row["next_poll_at"]),
            jobs_found_total=row["jobs_found_total"] or 0,
            active_jobs=row["active_jobs"] or 0,
            recent_activity=bool(row["recent_activity"]),
            predicted_hot=bool(row["predicted_hot"]),
        )

    async def save_company_state(self, state: CompanyState) -> None:
        await self.db.execute(
            """
            INSERT INTO company_state (
                slug, provider, etag, last_modified, last_success, last_error,
                consecutive_errors, poll_interval_seconds, next_poll_at,
                jobs_found_total, active_jobs, recent_activity, predicted_hot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                provider=excluded.provider,
                etag=excluded.etag,
                last_modified=excluded.last_modified,
                last_success=excluded.last_success,
                last_error=excluded.last_error,
                consecutive_errors=excluded.consecutive_errors,
                poll_interval_seconds=excluded.poll_interval_seconds,
                next_poll_at=excluded.next_poll_at,
                jobs_found_total=excluded.jobs_found_total,
                active_jobs=excluded.active_jobs,
                recent_activity=excluded.recent_activity,
                predicted_hot=excluded.predicted_hot
            """,
            (
                state.slug,
                state.provider.value,
                state.etag,
                state.last_modified,
                _dt(state.last_success),
                state.last_error,
                state.consecutive_errors,
                state.poll_interval_seconds,
                _dt(state.next_poll_at),
                state.jobs_found_total,
                state.active_jobs,
                1 if state.recent_activity else 0,
                1 if state.predicted_hot else 0,
            ),
        )
        await self.db.commit()

    async def list_company_states(self) -> list[CompanyState]:
        async with self.db.execute("SELECT * FROM company_state ORDER BY slug") as cur:
            rows = await cur.fetchall()
        result = []
        for row in rows:
            result.append(
                CompanyState(
                    slug=row["slug"],
                    provider=ATSProvider(row["provider"]),
                    etag=row["etag"],
                    last_modified=row["last_modified"],
                    last_success=_parse_dt(row["last_success"]),
                    last_error=row["last_error"],
                    consecutive_errors=row["consecutive_errors"] or 0,
                    poll_interval_seconds=row["poll_interval_seconds"] or 300,
                    next_poll_at=_parse_dt(row["next_poll_at"]),
                    jobs_found_total=row["jobs_found_total"] or 0,
                    active_jobs=row["active_jobs"] or 0,
                    recent_activity=bool(row["recent_activity"]),
                    predicted_hot=bool(row["predicted_hot"]),
                )
            )
        return result

    async def log_poll(
        self,
        company: str,
        provider: ATSProvider,
        *,
        total_jobs: int = 0,
        new_jobs: int = 0,
        error: str | None = None,
        duration_ms: float = 0,
        not_modified: bool = False,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO poll_log (company, provider, checked_at, total_jobs, new_jobs, error, duration_ms, not_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company,
                provider.value,
                datetime.utcnow().isoformat(),
                total_jobs,
                new_jobs,
                error,
                duration_ms,
                1 if not_modified else 0,
            ),
        )
        await self.db.commit()

    async def recent_poll_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.db.execute(
            """
            SELECT * FROM poll_log WHERE error IS NOT NULL
            ORDER BY checked_at DESC LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ----- History / prediction -----

    async def record_historical_opening(
        self,
        internship: Internship,
        *,
        company_slug: str | None = None,
    ) -> None:
        # Prefer stable slug so predict_hot_companies keys match CompanyConfig.slug
        key = company_slug or internship.company_slug or internship.company
        opened = internship.first_seen or datetime.utcnow()
        await self.db.execute(
            """
            INSERT OR IGNORE INTO historical_openings (company, year, opened_on, term, title)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                opened.year,
                opened.isoformat(),
                internship.term.value,
                internship.title,
            ),
        )
        await self.db.commit()

    async def historical_for_company(self, company: str) -> list[HistoricalOpening]:
        async with self.db.execute(
            """
            SELECT * FROM historical_openings WHERE company = ?
            ORDER BY opened_on
            """,
            (company,),
        ) as cur:
            rows = await cur.fetchall()
        out: list[HistoricalOpening] = []
        for r in rows:
            term = None
            if r["term"]:
                try:
                    term = InternshipTerm(r["term"])
                except ValueError:
                    term = None
            out.append(
                HistoricalOpening(
                    company=r["company"],
                    year=r["year"],
                    opened_on=_parse_dt(r["opened_on"]) or datetime.utcnow(),
                    term=term,
                    title=r["title"],
                )
            )
        return out

    async def all_historical(self) -> list[HistoricalOpening]:
        async with self.db.execute(
            "SELECT * FROM historical_openings ORDER BY company, opened_on"
        ) as cur:
            rows = await cur.fetchall()
        out: list[HistoricalOpening] = []
        for r in rows:
            term = None
            if r["term"]:
                try:
                    term = InternshipTerm(r["term"])
                except ValueError:
                    term = None
            out.append(
                HistoricalOpening(
                    company=r["company"],
                    year=r["year"],
                    opened_on=_parse_dt(r["opened_on"]) or datetime.utcnow(),
                    term=term,
                    title=r["title"],
                )
            )
        return out

    # ----- Applications -----

    async def upsert_application(self, record: ApplicationRecord) -> None:
        await self.db.execute(
            """
            INSERT INTO applications (dedupe_key, status, resume_version, notes, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                status=excluded.status,
                resume_version=excluded.resume_version,
                notes=excluded.notes,
                updated_at=excluded.updated_at
            """,
            (
                record.dedupe_key,
                record.status.value,
                record.resume_version,
                record.notes,
                _dt(record.updated_at),
            ),
        )
        await self.db.commit()

    async def get_application(self, dedupe_key: str) -> ApplicationRecord | None:
        async with self.db.execute(
            "SELECT * FROM applications WHERE dedupe_key = ?", (dedupe_key,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return ApplicationRecord(
            dedupe_key=row["dedupe_key"],
            status=ApplicationStatus(row["status"]),
            resume_version=row["resume_version"],
            notes=row["notes"],
            updated_at=_parse_dt(row["updated_at"]) or datetime.utcnow(),
        )

    # ----- Export -----

    async def export_json(self) -> list[dict[str, Any]]:
        jobs = await self.list_internships(active_only=False, limit=100_000)
        return [j.model_dump(mode="json") for j in jobs]

    async def export_csv_rows(self) -> list[dict[str, Any]]:
        jobs = await self.list_internships(active_only=False, limit=100_000)
        rows = []
        for j in jobs:
            rows.append(
                {
                    "company": j.company,
                    "title": j.title,
                    "location": j.location or "",
                    "url": j.url,
                    "term": j.term.value,
                    "provider": j.provider.value,
                    "score": j.score,
                    "first_seen": j.first_seen.isoformat() if j.first_seen else "",
                    "last_seen": j.last_seen.isoformat() if j.last_seen else "",
                    "is_active": j.is_active,
                    "remote": j.remote,
                }
            )
        return rows

    @staticmethod
    def _row_to_internship(row: aiosqlite.Row) -> Internship:
        raw = {}
        if row["raw_json"]:
            try:
                raw = json.loads(row["raw_json"])
            except json.JSONDecodeError:
                raw = {}
        remote_val = row["remote"]
        remote = None if remote_val is None else bool(remote_val)
        try:
            term = InternshipTerm(row["term"]) if row["term"] else InternshipTerm.UNKNOWN
        except ValueError:
            term = InternshipTerm.UNKNOWN
        return Internship(
            company=row["company"],
            title=row["title"],
            location=row["location"],
            url=row["url"],
            job_id=row["job_id"],
            provider=ATSProvider(row["provider"]),
            term=term,
            posted_date=_parse_dt(row["posted_date"]),
            employment_type=row["employment_type"],
            salary=row["salary"],
            remote=remote,
            first_seen=_parse_dt(row["first_seen"]) or datetime.utcnow(),
            last_seen=_parse_dt(row["last_seen"]) or datetime.utcnow(),
            description=row["description"],
            source=row["source"] or "ats",
            score=float(row["score"] or 0),
            is_active=bool(row["is_active"]),
            raw=raw,
        )
