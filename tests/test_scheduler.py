"""Scheduler adaptive schedule reconciliation tests."""

from datetime import datetime, timedelta

from core.models import ATSProvider, CompanyState
from core.scheduler import apply_adaptive_schedule


def test_never_scheduled_is_due_immediately():
    now = datetime(2026, 7, 21, 12, 0, 0)
    state = CompanyState(slug="acme", provider=ATSProvider.GREENHOUSE)
    due = apply_adaptive_schedule(state, interval=300, now=now)
    assert due is True
    assert state.next_poll_at == now
    assert state.poll_interval_seconds == 300


def test_shortened_interval_pulls_forward_stale_deadline():
    """Regression: not-due companies must not keep a long stale next_poll_at."""
    now = datetime(2026, 7, 21, 12, 0, 0)
    state = CompanyState(
        slug="acme",
        provider=ATSProvider.GREENHOUSE,
        poll_interval_seconds=1200,
        # Scheduled far out under the old off-hours interval
        next_poll_at=now + timedelta(seconds=1100),
    )
    # Interval shortened to business-hours 300s
    due = apply_adaptive_schedule(state, interval=300, now=now)
    assert due is False
    assert state.poll_interval_seconds == 300
    assert state.next_poll_at == now + timedelta(seconds=300)


def test_existing_near_deadline_not_pushed_later():
    now = datetime(2026, 7, 21, 12, 0, 0)
    original = now + timedelta(seconds=60)
    state = CompanyState(
        slug="acme",
        provider=ATSProvider.GREENHOUSE,
        poll_interval_seconds=300,
        next_poll_at=original,
    )
    due = apply_adaptive_schedule(state, interval=300, now=now)
    assert due is False
    assert state.next_poll_at == original


def test_past_deadline_is_due():
    now = datetime(2026, 7, 21, 12, 0, 0)
    state = CompanyState(
        slug="acme",
        provider=ATSProvider.GREENHOUSE,
        poll_interval_seconds=300,
        next_poll_at=now - timedelta(seconds=5),
    )
    assert apply_adaptive_schedule(state, interval=300, now=now) is True
