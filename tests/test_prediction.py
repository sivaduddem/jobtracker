"""Prediction / adaptive polling tests."""

from datetime import datetime, timedelta

from core.config import Settings
from core.models import ATSProvider, CompanyConfig, CompanyState, HistoricalOpening
from core.prediction import compute_poll_interval, predict_hot_companies


def test_business_hours_vs_off():
    settings = Settings(
        poll_business_hours=300,
        poll_off_hours=1200,
        poll_hot=120,
        poll_inactive=3600,
        business_hour_start=8,
        business_hour_end=20,
    )
    company = CompanyConfig(slug="x", provider=ATSProvider.GREENHOUSE)
    day = datetime(2026, 7, 21, 10, 0, 0)
    night = datetime(2026, 7, 21, 23, 0, 0)
    assert compute_poll_interval(company, None, settings, now=day) == 300
    assert compute_poll_interval(company, None, settings, now=night) == 1200


def test_compute_poll_interval_defaults_to_utc_not_local(monkeypatch):
    """Regression: missing `now` must use utcnow(), not local datetime.now()."""
    from core import prediction

    settings = Settings(
        poll_business_hours=300,
        poll_off_hours=1200,
        business_hour_start=8,
        business_hour_end=20,
    )
    company = CompanyConfig(slug="x", provider=ATSProvider.GREENHOUSE)

    calls: dict[str, int] = {"now": 0, "utcnow": 0}
    real_utcnow = datetime(2026, 7, 21, 23, 0, 0)  # UTC night → off hours
    real_now = datetime(2026, 7, 21, 10, 0, 0)  # would be business hours

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            calls["now"] += 1
            return real_now

        @classmethod
        def utcnow(cls):
            calls["utcnow"] += 1
            return real_utcnow

    monkeypatch.setattr(prediction, "datetime", FakeDateTime)
    assert compute_poll_interval(company, None, settings) == 1200
    assert calls["utcnow"] >= 1
    assert calls["now"] == 0


def test_hot_prediction_increases_frequency():
    settings = Settings(poll_hot=120, poll_business_hours=300, poll_off_hours=1200)
    company = CompanyConfig(slug="databricks", provider=ATSProvider.GREENHOUSE)
    state = CompanyState(
        slug="databricks",
        provider=ATSProvider.GREENHOUSE,
        predicted_hot=True,
    )
    interval = compute_poll_interval(
        company, state, settings, now=datetime(2026, 7, 21, 12, 0, 0)
    )
    assert interval == 120


def test_predict_hot_companies_near_anniversary():
    now = datetime(2026, 7, 25)
    history = [
        HistoricalOpening(company="Databricks", year=2024, opened_on=datetime(2024, 8, 6)),
        HistoricalOpening(company="Databricks", year=2025, opened_on=datetime(2025, 7, 31)),
        HistoricalOpening(company="Databricks", year=2026, opened_on=datetime(2026, 7, 25)),
        HistoricalOpening(company="OtherCo", year=2025, opened_on=datetime(2025, 1, 15)),
    ]
    hot = predict_hot_companies(history, now=now, window_days=5)
    assert "Databricks" in hot
    assert "databricks" in hot  # slug form for CompanyConfig.slug matching
    assert "OtherCo" not in hot
    assert "otherco" not in hot


def test_is_company_hot_matches_slug_against_display_name_history():
    """Regression: history stores display names; scheduler must match by slug."""
    from core.prediction import is_company_hot

    now = datetime(2026, 7, 25)
    history = [
        HistoricalOpening(company="Stripe", year=2025, opened_on=datetime(2025, 7, 22)),
        HistoricalOpening(company="Stripe", year=2026, opened_on=datetime(2026, 7, 24)),
    ]
    hot = predict_hot_companies(history, now=now, window_days=5)
    company = CompanyConfig(slug="stripe", name="Stripe", provider=ATSProvider.GREENHOUSE)
    assert is_company_hot(company, hot)

    # Slug-only config (no explicit name) should still match
    company_no_name = CompanyConfig(slug="stripe", provider=ATSProvider.GREENHOUSE)
    assert is_company_hot(company_no_name, hot)

    cold = CompanyConfig(slug="otherco", name="OtherCo", provider=ATSProvider.GREENHOUSE)
    assert not is_company_hot(cold, hot)
