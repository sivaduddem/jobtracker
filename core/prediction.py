"""Adaptive polling interval calculation and opening-window prediction."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

from core.config import Settings
from core.models import CompanyConfig, CompanyState, HistoricalOpening


def slugify_company(name: str) -> str:
    """Normalize a company display name or slug for prediction matching."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def is_business_hours(now: datetime | None, settings: Settings) -> bool:
    # Defaults to UTC to match scheduler / storage timestamps
    now = now or datetime.utcnow()
    return settings.business_hour_start <= now.hour < settings.business_hour_end


def compute_poll_interval(
    company: CompanyConfig,
    state: CompanyState | None,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    """
    Adaptive interval:
      - predicted hot / priority: poll_hot (default 2 min)
      - recent activity: business hours interval
      - business hours: poll_business_hours (5 min)
      - off hours: poll_off_hours (20 min)
      - inactive (no jobs ever, many errors): poll_inactive (60 min)

    `now` should be UTC (same clock as scheduler). Defaults to utcnow().
    """
    now = now or datetime.utcnow()
    base = (
        settings.poll_business_hours
        if is_business_hours(now, settings)
        else settings.poll_off_hours
    )

    if state and state.predicted_hot:
        return settings.poll_hot
    if company.priority >= 10:
        return settings.poll_hot
    if state and state.recent_activity:
        return min(base, settings.poll_business_hours)

    if state:
        if state.consecutive_errors >= 5:
            return settings.poll_inactive
        if state.jobs_found_total == 0 and state.last_success:
            # Never found internships — back off
            return max(base, settings.poll_inactive // 2)

    # Priority bump: each priority point shaves ~30s, floor at hot interval
    if company.priority > 0:
        return max(settings.poll_hot, base - company.priority * 30)

    return base


def predict_hot_companies(
    history: list[HistoricalOpening],
    *,
    now: datetime | None = None,
    window_days: int = 5,
) -> set[str]:
    """
    Companies whose historical first-seen dates cluster near `now` (±window_days).

    Returns a set of match keys: raw stored names, casefolded names, and slugs.
    History may contain display names ("Stripe") or slugs ("stripe"); callers
    should test membership with `is_company_hot()`.
    """
    now = now or datetime.utcnow()
    by_company: dict[str, list[datetime]] = defaultdict(list)
    for h in history:
        by_company[h.company].append(h.opened_on)

    hot_names: set[str] = set()
    for company, dates in by_company.items():
        if len(dates) < 1:
            continue
        # Use day-of-year averages across years
        doys = [d.timetuple().tm_yday for d in dates]
        avg_doy = mean(doys)
        current_doy = now.timetuple().tm_yday
        # Circular distance on day-of-year
        diff = abs(current_doy - avg_doy)
        diff = min(diff, 365 - diff)
        if diff <= window_days:
            hot_names.add(company)
        # Also: if last year's opening anniversary is within window
        for d in dates:
            anniversary = d.replace(year=now.year)
            if abs((anniversary - now).days) <= window_days:
                hot_names.add(company)

    # Expand so slug ("stripe") matches history keyed by display name ("Stripe")
    hot: set[str] = set()
    for name in hot_names:
        hot.add(name)
        hot.add(name.casefold())
        slug = slugify_company(name)
        if slug:
            hot.add(slug)
    return hot


def is_company_hot(company: CompanyConfig, hot: set[str]) -> bool:
    """True if this monitored company appears in a predict_hot_companies() set."""
    if company.slug in hot or company.slug.casefold() in hot:
        return True
    display = company.display_name
    if display in hot or display.casefold() in hot:
        return True
    slug_from_display = slugify_company(display)
    return bool(slug_from_display and slug_from_display in hot)


def days_until_predicted_opening(
    company: str,
    history: list[HistoricalOpening],
    *,
    now: datetime | None = None,
) -> int | None:
    now = now or datetime.utcnow()
    dates = [h.opened_on for h in history if h.company == company]
    if not dates:
        return None
    doys = [d.timetuple().tm_yday for d in dates]
    avg_doy = int(mean(doys))
    year = now.year
    predicted = datetime(year, 1, 1) + timedelta(days=avg_doy - 1)
    if predicted < now - timedelta(days=30):
        predicted = datetime(year + 1, 1, 1) + timedelta(days=avg_doy - 1)
    return (predicted.date() - now.date()).days
