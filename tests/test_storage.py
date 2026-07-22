"""Storage + config integration tests."""

from pathlib import Path

import pytest
import yaml

from core.config import load_companies
from core.models import ATSProvider, Internship, InternshipTerm
from database.sqlite import Storage


@pytest.mark.asyncio
async def test_storage_upsert_and_dedupe(tmp_path: Path):
    db = Storage(tmp_path / "test.db")
    await db.connect()
    job = Internship(
        company="Stripe",
        title="Software Engineer Intern",
        url="https://boards.greenhouse.io/stripe/jobs/1",
        job_id="1",
        provider=ATSProvider.GREENHOUSE,
        term=InternshipTerm.SUMMER_2027,
        score=100,
    )
    is_new, should_notify = await db.upsert_internship(
        job, notify=True, company_slug="stripe"
    )
    assert is_new and should_notify

    is_new2, should_notify2 = await db.upsert_internship(job, notify=True)
    assert not is_new2 and not should_notify2

    jobs = await db.list_internships()
    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer Intern"
    assert jobs[0].company_slug == "stripe"

    removed = await db.mark_missing_inactive("Stripe", ATSProvider.GREENHOUSE, set())
    assert removed == 1
    active = await db.list_internships(active_only=True)
    assert len(active) == 0
    await db.close()


@pytest.mark.asyncio
async def test_mark_missing_inactive_by_slug_matches_display_name_rows(tmp_path: Path):
    """Regression: scheduler passes slug; DB stores display name in company."""
    db = Storage(tmp_path / "test_slug.db")
    await db.connect()
    job = Internship(
        company="Stripe",
        title="Software Engineer Intern",
        url="https://boards.greenhouse.io/stripe/jobs/99",
        job_id="99",
        provider=ATSProvider.GREENHOUSE,
        term=InternshipTerm.SUMMER_2027,
        score=100,
    )
    await db.upsert_internship(job, notify=True, company_slug="stripe")

    # Scheduler historically called with slug only — must still deactivate
    removed = await db.mark_missing_inactive(
        "stripe", ATSProvider.GREENHOUSE, set(), company_slug="stripe"
    )
    assert removed == 1
    assert await db.list_internships(active_only=True) == []
    await db.close()


@pytest.mark.asyncio
async def test_url_hash_collision_updates_company_slug(tmp_path: Path):
    """URL-hash collision path must populate company_slug like INSERT/UPDATE."""
    db = Storage(tmp_path / "test_url_slug.db")
    await db.connect()
    first = Internship(
        company="Stripe",
        title="Software Engineer Intern",
        url="https://boards.greenhouse.io/stripe/jobs/abc",
        job_id="old-id",
        provider=ATSProvider.GREENHOUSE,
        term=InternshipTerm.SUMMER_2027,
        score=100,
    )
    await db.upsert_internship(first, notify=True)  # no slug on first insert
    rows = await db.list_internships()
    assert rows[0].company_slug is None

    # Same URL, different job_id → collision update should set slug
    second = Internship(
        company="Stripe",
        title="Software Engineer Intern",
        url="https://boards.greenhouse.io/stripe/jobs/abc",
        job_id="new-id",
        provider=ATSProvider.GREENHOUSE,
        term=InternshipTerm.SUMMER_2027,
        score=98,
    )
    is_new, _ = await db.upsert_internship(second, notify=True, company_slug="stripe")
    assert is_new is False
    rows = await db.list_internships()
    assert len(rows) == 1
    assert rows[0].company_slug == "stripe"
    assert rows[0].score == 98
    await db.close()


def test_load_companies_yaml(tmp_path: Path):
    path = tmp_path / "companies.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "companies": {
                    "stripe": {"provider": "greenhouse", "name": "Stripe"},
                    "cursor": {
                        "provider": "ashby",
                        "board_token": "anysphere",
                        "name": "Cursor",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    companies = load_companies(path)
    assert len(companies) == 2
    by_slug = {c.slug: c for c in companies}
    assert by_slug["stripe"].provider == ATSProvider.GREENHOUSE
    assert by_slug["cursor"].board_token == "anysphere"
