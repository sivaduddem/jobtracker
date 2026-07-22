"""Deduplication tests."""

from core.dedupe import is_duplicate, keys_for
from core.models import ATSProvider, Internship


def _job(job_id: str, url: str, company: str = "Acme") -> Internship:
    return Internship(
        company=company,
        title="Software Engineer Intern",
        url=url,
        job_id=job_id,
        provider=ATSProvider.GREENHOUSE,
    )


def test_dedupe_key_stable():
    a = _job("123", "https://boards.greenhouse.io/acme/jobs/123")
    b = _job("123", "https://boards.greenhouse.io/acme/jobs/123")
    assert a.dedupe_key == b.dedupe_key


def test_is_duplicate_by_dedupe_key():
    job = _job("99", "https://example.com/jobs/99")
    known = keys_for(job)
    assert is_duplicate(known, job)
    other = _job("100", "https://example.com/jobs/100")
    assert not is_duplicate(known, other)


def test_url_hash_collision_detection():
    a = _job("1", "https://Example.com/Job/ABC")
    b = _job("2", "https://example.com/job/abc")  # different job_id, same URL
    # Same URL hash should flag duplicate via url_hash set
    known = {a.url_hash}
    assert is_duplicate(known, b)
