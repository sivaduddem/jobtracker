"""Internship filtering, term classification, and ranking."""

from __future__ import annotations

import re
from datetime import datetime

from core.config import (
    EXCLUDE_PATTERNS,
    INCLUDE_PATTERNS,
    RANKING_RULES,
    TERM_PATTERNS,
)
from core.models import Internship, InternshipTerm

_INCLUDE = [re.compile(p, re.IGNORECASE) for p in INCLUDE_PATTERNS]
_EXCLUDE = [re.compile(p, re.IGNORECASE) for p in EXCLUDE_PATTERNS]
_RANK = [(re.compile(r["pattern"], re.IGNORECASE), float(r["score"])) for r in RANKING_RULES]
_TERMS = {
    term: [re.compile(p, re.IGNORECASE) for p in pats]
    for term, pats in TERM_PATTERNS.items()
}

# Hard excludes in the TITLE always disqualify
_HARD_TITLE_EXCLUDE = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bsenior\b",
        r"\bstaff\b",
        r"\bprincipal\b",
        r"\bmanager\b",
        r"\bdirector\b",
        r"\bmarketing\b",
        r"\bsales\b",
        r"\brecruiter\b",
        r"\baccount\s*executive\b",
        r"\bcoordinator\b",
        r"\bspecialist\b",
        r"\banalyst\b(?!.*engineer)",  # business analyst etc., not eng
    ]
]


def is_internship_candidate(title: str, description: str | None = None) -> bool:
    """
    Return True if this looks like a relevant engineering internship.

    Title is authoritative — description alone cannot qualify a posting
    (ATS descriptions often mention internship programs generically).
    """
    title = title or ""
    # Word-boundary matters: "Internal" / "International" must NOT match
    if not re.search(r"\bintern(?:s|ship)?\b", title, re.IGNORECASE):
        return False

    if any(rx.search(title) for rx in _HARD_TITLE_EXCLUDE):
        return False

    if any(rx.search(title) for rx in _EXCLUDE):
        return False

    # Include patterns must match the TITLE (not just buried description text)
    if any(rx.search(title) for rx in _INCLUDE):
        return True

    # Allow description to reinforce only when title already says Intern
    # and has an engineering signal word
    if re.search(
        r"\b(software|swe|backend|frontend|full[\s-]*stack|platform|infrastructure|"
        r"systems|security|ml|machine\s*learning|data\s*eng|research\s*eng|engineer)\b",
        title,
        re.IGNORECASE,
    ):
        return True

    return False


def classify_term(
    title: str,
    description: str | None = None,
    posted_date: datetime | None = None,
) -> InternshipTerm:
    """Infer internship term from title/description/metadata."""
    blob = f"{title}\n{description or ''}"
    for term, patterns in _TERMS.items():
        if any(rx.search(blob) for rx in patterns):
            return term

    # Only weak date heuristic — prefer Unknown over wrong labels
    if posted_date and posted_date.year == 2026 and posted_date.month >= 5:
        # Summer 2027 recruiting often opens mid-2026; don't auto-label
        # unless title/description already hinted above.
        pass

    return InternshipTerm.UNKNOWN


def score_internship(internship: Internship) -> float:
    """Configurable weighted ranking. 0 = non-engineering / irrelevant."""
    if not is_internship_candidate(internship.title, internship.description):
        return 0.0

    # Score from TITLE primarily so description noise can't inflate rank
    best = 0.0
    for rx, weight in _RANK:
        if rx.search(internship.title):
            best = max(best, weight)

    if best <= 0:
        # Engineering intern title without a specific rule → mid score
        if re.search(r"engineer", internship.title, re.IGNORECASE):
            best = 60.0
        else:
            return 0.0

    # Term boost only when we already matched an eng intern rule
    if internship.term != InternshipTerm.UNKNOWN:
        best = min(100.0, best + 5.0)
        if internship.term == InternshipTerm.SUMMER_2027 and best >= 95:
            best = 100.0

    if internship.remote:
        best = min(100.0, best + 1.0)

    return best


def enrich_internship(internship: Internship) -> Internship | None:
    """
    Classify term, score, and drop non-matches.
    Returns None if the posting should be ignored.
    """
    if not is_internship_candidate(internship.title, internship.description):
        return None

    internship.term = classify_term(
        internship.title, internship.description, internship.posted_date
    )
    internship.score = score_internship(internship)
    if internship.score < 40:
        return None
    return internship
