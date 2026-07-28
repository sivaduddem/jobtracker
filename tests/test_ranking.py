"""Unit tests — ranking, term classification, filters."""

from core.models import ATSProvider, Internship, InternshipTerm
from core.ranking import (
    classify_term,
    enrich_internship,
    is_internship_candidate,
    is_us_or_canada_location,
    score_internship,
)


def test_include_swe_intern():
    assert is_internship_candidate("Software Engineer Intern")
    assert is_internship_candidate("SWE Intern - Summer 2027")
    assert is_internship_candidate("Platform Engineering Intern")
    assert is_internship_candidate("Backend Intern")


def test_exclude_senior_and_non_eng():
    assert not is_internship_candidate("Senior Software Engineer")
    assert not is_internship_candidate("Staff Software Engineer")
    assert not is_internship_candidate("Marketing Intern")
    assert not is_internship_candidate("Sales Intern")
    assert not is_internship_candidate("Product Manager Intern")
    # "Internal" / "International" must not match "intern"
    assert not is_internship_candidate("Software Engineer, Internal Systems")
    assert not is_internship_candidate("Software Engineer, International")
    assert not is_internship_candidate("Internal Product Engineer")


def test_us_canada_location_filter():
    assert is_us_or_canada_location("Mountain View, CA, USA; Atlanta, GA, USA; +29 more")
    assert is_us_or_canada_location("Toronto, ON, Canada")
    assert is_us_or_canada_location("Seattle, WA")
    assert is_us_or_canada_location("Remote - United States", remote=True)
    assert is_us_or_canada_location("USA Remote")
    # Strict: missing / unknown / foreign rejected
    assert not is_us_or_canada_location(None)
    assert not is_us_or_canada_location("")
    assert not is_us_or_canada_location("Remote", remote=True)
    assert not is_us_or_canada_location("Bengaluru, India")
    assert not is_us_or_canada_location("London, UK")
    assert not is_us_or_canada_location("Warsaw, Poland")
    assert not is_us_or_canada_location("Lisbon, Portugal")
    assert not is_us_or_canada_location("Bellville, South Africa")
    # URL path fallback (Workday)
    assert not is_us_or_canada_location(
        None,
        url="https://salesforce.wd12.myworkdayjobs.com/External_Career_Site/job/India---Bangalore/Summer-2027-Intern---Software-Engineer_JR337715",
    )
    assert not is_us_or_canada_location(
        None,
        url="https://motorolasolutions.wd5.myworkdayjobs.com/Careers/job/Bellville-South-Africa-ZSA06/Field-Engineer-Intern-Graduate--Sub-Saharan-Africa_R63840",
    )
    assert is_us_or_canada_location(
        None,
        url="https://salesforce.wd12.myworkdayjobs.com/External_Career_Site/job/California---San-Francisco/Summer-2027-Intern---Software-Engineer_JR1",
    )


def test_enrich_drops_foreign_locations(monkeypatch):
    from core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LOCATION_FILTER", "us_canada")
    get_settings.cache_clear()

    foreign = Internship(
        company="Stripe",
        title="Software Engineer, Intern",
        location="Bengaluru, India",
        url="https://example.com/in",
        job_id="in-1",
        provider=ATSProvider.GREENHOUSE,
    )
    assert enrich_internship(foreign) is None

    portugal = Internship(
        company="Cloudflare",
        title="Research Engineer Intern (Fall 2026)",
        location="Lisbon, Portugal",
        url="https://boards.greenhouse.io/cloudflare/jobs/8089400",
        job_id="8089400",
        provider=ATSProvider.GREENHOUSE,
    )
    assert enrich_internship(portugal) is None

    india_url = Internship(
        company="Salesforce",
        title="Summer 2027 Intern - Software Engineer",
        location=None,
        url="https://salesforce.wd12.myworkdayjobs.com/External_Career_Site/job/India---Bangalore/Summer-2027-Intern---Software-Engineer_JR337715",
        job_id="JR337715",
        provider=ATSProvider.WORKDAY,
    )
    assert enrich_internship(india_url) is None

    us = Internship(
        company="Google",
        title="Software Engineering Intern, BS, Summer 2027",
        location="Mountain View, CA, USA; Atlanta, GA, USA",
        url="https://example.com/us",
        job_id="us-1",
        provider=ATSProvider.GOOGLE,
    )
    enriched = enrich_internship(us)
    assert enriched is not None
    assert enriched.term == InternshipTerm.SUMMER_2027
    get_settings.cache_clear()


def test_classify_terms():
    assert classify_term("Software Engineer Intern - Summer 2027") == InternshipTerm.SUMMER_2027
    assert classify_term("SWE Intern Fall 2026") == InternshipTerm.FALL_2026
    assert classify_term("Winter 2027 Software Engineering Intern") == InternshipTerm.WINTER_2027
    assert classify_term("Spring 2027 Intern") == InternshipTerm.SPRING_2027


def test_ranking_scores():
    def mk(title: str) -> Internship:
        return Internship(
            company="Test",
            title=title,
            url="https://example.com/1",
            job_id="1",
            provider=ATSProvider.GREENHOUSE,
            term=classify_term(title),
        )

    assert score_internship(mk("Software Engineer Intern Summer 2027")) >= 100
    assert score_internship(mk("Platform Engineering Intern")) >= 98
    assert score_internship(mk("Infrastructure Intern")) >= 97
    assert score_internship(mk("Backend Intern")) >= 95
    assert score_internship(mk("Full Stack Intern")) >= 80
    assert score_internship(mk("Frontend Intern")) == 40


def test_enrich_drops_non_matches():
    bad = Internship(
        company="X",
        title="Senior Software Engineer",
        url="https://example.com/2",
        job_id="2",
        provider=ATSProvider.ASHBY,
    )
    assert enrich_internship(bad) is None

    good = Internship(
        company="X",
        title="Software Engineer Intern - Summer 2027",
        location="San Francisco, CA",
        url="https://example.com/3",
        job_id="3",
        provider=ATSProvider.ASHBY,
    )
    enriched = enrich_internship(good)
    assert enriched is not None
    assert enriched.term == InternshipTerm.SUMMER_2027
    assert enriched.score >= 100
