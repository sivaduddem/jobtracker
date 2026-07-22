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
    is_new, should_notify = await db.upsert_internship(job, notify=True)
    assert is_new and should_notify

    is_new2, should_notify2 = await db.upsert_internship(job, notify=True)
    assert not is_new2 and not should_notify2

    jobs = await db.list_internships()
    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer Intern"

    removed = await db.mark_missing_inactive("Stripe", ATSProvider.GREENHOUSE, set())
    assert removed == 1
    active = await db.list_internships(active_only=True)
    assert len(active) == 0
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
