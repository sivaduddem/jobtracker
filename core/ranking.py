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
        r"manila|philippines|vietnam|ho\s+chi\s+minh|"
        r"south\s+africa|cape\s+town|johannesburg|bellville|"
        r"nigeria|kenya|egypt|uae|dubai|abu\s+dhabi|"
        r"saudi|riyadh|qatar|kuwait|romania|bucharest|"
        r"hungary|budapest|greece|athens|turkey|istanbul|"
        r"ukraine|kyiv|russia|moscow|pakistan|karachi|"
        r"bangladesh|dhaka|malaysia|kuala\s+lumpur|"
        r"emea|apac|latam|europe|asia|africa)\b",
    ]
]

# Remote is only OK when explicitly tied to US/Canada.
_REMOTE_US_CANADA = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bremote\b.*\b(united\s+states|usa|u\.s\.a?\.?|canada|canadian)\b",
        r"\b(united\s+states|usa|u\.s\.a?\.?|canada|canadian)\b.*\bremote\b",
        r"\b(us|usa|canada)[\s\-_/]*remote\b",
        r"\bremote[\s\-_/]*(us|usa|canada)\b",
    ]
]


def is_undergrad_eligible(title: str, description: str | None = None) -> bool:
    """
    Keep undergrad-eligible roles.

    Reject PhD-only (or doctoral-only) postings. Keep roles that also hire
    undergrads even if masters/PhD are listed (e.g. BS/MS/PhD).
    """
    blob = f"{title}\n{description or ''}"

    undergrad = re.search(
        r"\b("
        r"undergrad(?:uate)?s?|"
        r"bachelor'?s?|"
        r"bachelors|"
        r"bs|"
        r"b\.s\.?|"
        r"ba|"
        r"b\.a\.?|"
        r"bsc|"
        r"undergraduate\s+student"
        r")\b",
        blob,
        re.IGNORECASE,
    )
    phd = re.search(
        r"\b("
        r"ph\.?\s*d\.?|"
        r"phd|"
        r"doctoral|"
        r"doctorate|"
        r"post[\s-]*doc(?:toral)?"
        r")\b",
        blob,
        re.IGNORECASE,
    )

    if not phd:
        return True
    # PhD mentioned — only keep when undergrad/bachelor track is also open
    return bool(undergrad)


def is_cs_track_internship(title: str) -> bool:
    """True for SWE/SDE/ML/AI/embedded/firmware-style intern titles."""
    return any(rx.search(title or "") for rx in _INCLUDE)


def is_internship_candidate(title: str, description: str | None = None) -> bool:
    title = title or ""
    if not re.search(r"\bintern(?:s|ship)?\b", title, re.IGNORECASE):
        return False
    if any(rx.search(title) for rx in _HARD_TITLE_EXCLUDE):
        return False
    if any(rx.search(title) for rx in _EXCLUDE):
        return False
    if not is_cs_track_internship(title):
        return False
    if not is_undergrad_eligible(title, description):
        return False
    return True


def location_blob_from_url(url: str | None) -> str:
    """Pull location-ish tokens from career URLs (esp. Workday path segments)."""
    if not url:
        return ""
    # Workday: /job/India---Bangalore/Title_REQ or /job/Bellville-South-Africa-ZSA06/...
    m = re.search(r"/job/([^/]+)/", url, re.IGNORECASE)
    if m:
        return m.group(1).replace("---", " - ").replace("-", " ")
    return url


def is_us_or_canada_location(
    location: str | None,
    *,
    remote: bool | None = None,
    url: str | None = None,
) -> bool:
    """
    Strict US/Canada allowlist.

    A job passes only when location (or URL path fallback) positively matches
    the United States or Canada. Missing/unknown locations are rejected.
    Remote roles pass only when explicitly US/Canada remote.
    Multi-location strings that include at least one US/Canada site are kept,
    unless they are purely foreign.
    """
    text = (location or "").strip()
    url_blob = location_blob_from_url(url)
    combined = f"{text} {url_blob}".strip()

    if not combined:
        return False

    # Explicit foreign with no US/Canada signal → reject
    has_us_ca = any(rx.search(combined) for rx in _US_CANADA_POSITIVE)
    has_foreign = any(rx.search(combined) for rx in _FOREIGN_ONLY)

    if has_us_ca:
        return True

    if remote or re.search(r"\bremote\b", combined, re.IGNORECASE):
        return any(rx.search(combined) for rx in _REMOTE_US_CANADA)

    if has_foreign:
        return False

    # Unknown city/country with no US/Canada markers → reject (strict)
    return False


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
        if not is_us_or_canada_location(
            internship.location,
            remote=internship.remote,
            url=internship.url,
        ):
            return None

    internship.term = classify_term(
        internship.title, internship.description, internship.posted_date
    )
    internship.score = score_internship(internship)
    if internship.score < 40:
        return None
    return internship
