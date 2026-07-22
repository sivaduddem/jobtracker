"""Provider normalization unit tests (no network)."""

from core.models import ATSProvider, CompanyConfig
from providers.ashby import AshbyProvider
from providers.greenhouse import GreenhouseProvider
from providers.lever import LeverProvider


def test_greenhouse_normalize():
    p = GreenhouseProvider.__new__(GreenhouseProvider)
    company = CompanyConfig(slug="stripe", name="Stripe", provider=ATSProvider.GREENHOUSE)
    job = {
        "id": 12345,
        "title": "Software Engineer Intern",
        "absolute_url": "https://boards.greenhouse.io/stripe/jobs/12345",
        "location": {"name": "Remote"},
        "updated_at": "2026-07-01T12:00:00Z",
        "content": "Summer 2027 internship",
    }
    intern = p._normalize(company, job)
    assert intern.job_id == "12345"
    assert intern.company == "Stripe"
    assert intern.provider == ATSProvider.GREENHOUSE
    assert intern.remote is True


def test_lever_normalize():
    p = LeverProvider.__new__(LeverProvider)
    company = CompanyConfig(slug="netflix", name="Netflix", provider=ATSProvider.LEVER)
    job = {
        "id": "abc",
        "text": "Software Engineer Intern",
        "hostedUrl": "https://jobs.lever.co/netflix/abc",
        "categories": {"location": "Los Gatos", "commitment": "Intern"},
        "createdAt": 1_720_000_000_000,
        "workplaceType": "hybrid",
        "descriptionPlain": "Build things",
    }
    intern = p._normalize(company, job)
    assert intern.job_id == "abc"
    assert intern.location == "Los Gatos"
    assert intern.provider == ATSProvider.LEVER


def test_ashby_normalize():
    p = AshbyProvider.__new__(AshbyProvider)
    company = CompanyConfig(
        slug="cursor", name="Cursor", provider=ATSProvider.ASHBY, board_token="anysphere"
    )
    job = {
        "id": "job-1",
        "title": "Software Engineer Intern",
        "jobUrl": "https://jobs.ashbyhq.com/anysphere/job-1",
        "location": "San Francisco",
        "isRemote": False,
        "publishedAt": "2026-06-15T00:00:00Z",
    }
    intern = p._normalize(company, job, "anysphere")
    assert intern.job_id == "job-1"
    assert intern.url.endswith("job-1")
    assert intern.provider == ATSProvider.ASHBY


def test_google_title_from_slug():
    from providers.google import _title_from_slug

    title = _title_from_slug("software-engineering-intern-bs-summer-2027")
    assert "Software" in title
    assert "Intern" in title
    assert "2027" in title
