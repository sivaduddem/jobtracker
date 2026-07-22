"""Internship filtering, term classification, ranking, and geo filters."""

from __future__ import annotations

import re
from datetime import datetime

from core.config import (
    EXCLUDE_PATTERNS,
    INCLUDE_PATTERNS,
    RANKING_RULES,
    TERM_PATTERNS,
    get_settings,
)
from core.models import Internship, InternshipTerm

_INCLUDE = [re.compile(p, re.IGNORECASE) for p in INCLUDE_PATTERNS]
_EXCLUDE = [re.compile(p, re.IGNORECASE) for p in EXCLUDE_PATTERNS]
_RANK = [(re.compile(r["pattern"], re.IGNORECASE), float(r["score"])) for r in RANKING_RULES]
_TERMS = {
    term: [re.compile(p, re.IGNORECASE) for p in pats]
    for term, pats in TERM_PATTERNS.items()
}

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
        r"\banalyst\b(?!.*engineer)",
    ]
]

_US_CANADA_POSITIVE = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bunited\s+states\b",
        r"\busa\b",
        r"\bu\.s\.a\.?\b",
        r"\bu\.s\.\b",
        r",\s*us\b",
        r"\bcanada\b",
        r"\bcanadian\b",
        r"\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
        r"delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|"
        r"kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
        r"mississippi|missouri|montana|nebraska|nevada|new\s+hampshire|"
        r"new\s+jersey|new\s+mexico|new\s+york|north\s+carolina|north\s+dakota|"
        r"ohio|oklahoma|oregon|pennsylvania|rhode\s+island|south\s+carolina|"
        r"south\s+dakota|tennessee|texas|utah|vermont|virginia|washington|"
        r"west\s+virginia|wisconsin|wyoming|district\s+of\s+columbia)\b",
        r",\s*(A[LKZR]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEHINOST]|"
        r"N[CDEHJMVY]|O[HKR]|P[AR]|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b",
        r"\b(ontario|quebec|british\s+columbia|alberta|manitoba|saskatchewan|"
        r"nova\s+scotia|new\s+brunswick|newfoundland|prince\s+edward|"
        r"toronto|vancouver|montreal|ottawa|calgary|waterloo|kitchener|"
        r"victoria|edmonton|winnipeg|halifax)\b",
        r",\s*(ON|BC|AB|MB|SK|NS|NB|NL|PE|QC|YT|NT|NU)\b",
        r"\b(mountain\s+view|sunnyvale|cupertino|palo\s+alto|menlo\s+park|"
        r"san\s+francisco|san\s+jose|seattle|bellevue|redmond|kirkland|"
        r"new\s+york\s*city|\bnyc\b|austin|boston|cambridge|chicago|"
        r"atlanta|denver|boulder|los\s+angeles|irvine|san\s+diego|"
        r"pittsburgh|raleigh|durham|reston|portland|madison|"
        r"playa\s+vista|goleta|santa\s+cruz)\b",
    ]
]

_FOREIGN_ONLY = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(india|bengaluru|bangalore|hyderabad|mumbai|chennai|pune|delhi|"
        r"gurgaon|gurugram|noida)\b",
        r"\b(united\s+kingdom|\buk\b|london|manchester|edinburgh|dublin|ireland)\b",
        r"\b(germany|berlin|munich|frankfurt|hamburg|zurich|switzerland|"
        r"amsterdam|netherlands|paris|france|stockholm|sweden|oslo|norway|"
        r"copenhagen|denmark|helsinki|finland|warsaw|poland|prague|"
        r"czech|vienna|austria|brussels|belgium|madrid|spain|milan|"
        r"italy|lisbon|portugal|tel\s+aviv|israel|singapore|hong\s+kong|"
        r"tokyo|japan|seoul|korea|sydney|melbourne|australia|"
        r"auckland|new\s+zealand|sao\s+paulo|brazil|mexico\s+city|"
        r"argentina|chile|colombia|taiwan|taipei|shanghai|beijing|"
        r"shenzhen|china|jakarta|indonesia|bangkok|thailand|"
        r"manila|philippines|vietnam|ho\s+chi\s+minh)\b",
    ]
]


def is_internship_candidate(title: str, description: str | None = None) -> bool:
    title = title or ""
    if not re.search(r"\bintern(?:s|ship)?\b", title, re.IGNORECASE):
        return False
    if any(rx.search(title) for rx in _HARD_TITLE_EXCLUDE):
        return False
    if any(rx.search(title) for rx in _EXCLUDE):
        return False
    if any(rx.search(title) for rx in _INCLUDE):
        return True
    if re.search(
        r"\b(software|swe|backend|frontend|full[\s-]*stack|platform|infrastructure|"
        r"systems|security|ml|machine\s*learning|data\s*eng|research\s*eng|engineer)\b",
        title,
        re.IGNORECASE,
    ):
        return True
    return False


def is_us_or_canada_location(
    location: str | None,
    *,
    remote: bool | None = None,
) -> bool:
    """
    True if acceptable under a US/Canada-only filter.

    Multi-location strings that include any US/Canada site are kept.
    Purely foreign locations are rejected. Remote / missing location is kept.
    """
    if remote:
        return True
    if not location or not location.strip():
        return True

    text = location.strip()
    if any(rx.search(text) for rx in _US_CANADA_POSITIVE):
        return True
    if any(rx.search(text) for rx in _FOREIGN_ONLY):
        return False
    return True


def classify_term(
    title: str,
    description: str | None = None,
    posted_date: datetime | None = None,
) -> InternshipTerm:
    blob = f"{title}\n{description or ''}"
    for term, patterns in _TERMS.items():
        if any(rx.search(blob) for rx in patterns):
            return term
    return InternshipTerm.UNKNOWN


def score_internship(internship: Internship) -> float:
    if not is_internship_candidate(internship.title, internship.description):
        return 0.0

    best = 0.0
    for rx, weight in _RANK:
        if rx.search(internship.title):
            best = max(best, weight)

    if best <= 0:
        if re.search(r"engineer", internship.title, re.IGNORECASE):
            best = 60.0
        else:
            return 0.0

    if internship.term != InternshipTerm.UNKNOWN:
        best = min(100.0, best + 5.0)
        if internship.term == InternshipTerm.SUMMER_2027 and best >= 95:
            best = 100.0

    if internship.remote:
        best = min(100.0, best + 1.0)

    return best


def enrich_internship(internship: Internship) -> Internship | None:
    if not is_internship_candidate(internship.title, internship.description):
        return None

    settings = get_settings()
    if settings.location_filter.lower() in {"us_canada", "us-canada", "na"}:
        if not is_us_or_canada_location(internship.location, remote=internship.remote):
            return None

    internship.term = classify_term(
        internship.title, internship.description, internship.posted_date
    )
    internship.score = score_internship(internship)
    if internship.score < 40:
        return None
    return internship
