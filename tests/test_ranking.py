"""Unit tests — ranking, term classification, filters."""

from datetime import datetime

from core.models import ATSProvider, Internship, InternshipTerm
from core.ranking import (
    classify_term,
    enrich_internship,
    is_internship_candidate,
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
        url="https://example.com/3",
        job_id="3",
        provider=ATSProvider.ASHBY,
    )
    enriched = enrich_internship(good)
    assert enriched is not None
    assert enriched.term == InternshipTerm.SUMMER_2027
    assert enriched.score >= 100
