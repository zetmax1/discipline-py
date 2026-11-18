"""
F-05: today / week / month boundaries use the user's zone from the internal JWT.
The clock is frozen at Sunday 2026-10-25 19:30 UTC, which is already
Monday 2026-10-26 00:30 in Asia/Tashkent (UTC+5).
"""

from datetime import UTC, date, datetime

import pytest

from app import reports, timeutil
from app.smart_schedule.generator import ScheduleGenerator

TASHKENT = "Asia/Tashkent"
SUNDAY_1930_UTC = datetime(2026, 10, 25, 19, 30, tzinfo=UTC)


@pytest.fixture
def frozen(monkeypatch):
    def freeze(instant):
        monkeypatch.setattr(timeutil, "_utcnow", lambda: instant)
    freeze(SUNDAY_1930_UTC)
    return freeze


@pytest.fixture
def ranges(monkeypatch):
    """Capture every (start, end) date range the reports query."""
    seen = []

    def fake_load(db, user_id, start, end):
        seen.append((start.isoformat(), end.isoformat()))
        return []

    monkeypatch.setattr(reports, "load_blocks", fake_load)
    return seen


def test_half_past_midnight_tashkent_is_the_next_day(frozen):
    assert timeutil.local_today(TASHKENT) == date(2026, 10, 26)
    assert timeutil.local_today("UTC") == date(2026, 10, 25)


def test_today_report_uses_local_date(frozen, ranges):
    assert reports.today_report(None, 1, TASHKENT)["date"] == "2026-10-26"
    assert reports.today_report(None, 1, "UTC")["date"] == "2026-10-25"


def test_week_report_uses_local_week(frozen, ranges):
    r = reports.period_report(None, 1, TASHKENT, "week")
    assert r["start_date"] == "2026-10-26"                       # this week starts Monday 26th locally
    assert ("2026-10-19", "2026-10-25") in ranges                # previous week for comparison


def test_week_report_in_utc_is_still_previous_week(frozen, ranges):
    assert reports.period_report(None, 1, "UTC", "week")["start_date"] == "2026-10-19"


def test_month_boundary_uses_local_month(frozen, ranges):
    frozen(datetime(2026, 10, 31, 19, 30, tzinfo=UTC))  # 2026-11-01 00:30 Tashkent
    r = reports.period_report(None, 1, TASHKENT, "month")
    assert r["start_date"] == "2026-11-01"
    assert ("2026-10-01", "2026-10-31") in ranges                # previous month comparison


def test_trailing_windows_end_on_local_today(frozen, ranges):
    r = reports.focus_patterns(None, 1, TASHKENT, 7)
    assert (r["start_date"], r["end_date"]) == ("2026-10-20", "2026-10-26")
    assert ranges[0] == ("2026-10-20", "2026-10-26")


def test_schedule_history_cutoff_uses_local_date(frozen):
    gen = ScheduleGenerator(db=None, user_id=1, tz=TASHKENT)
    assert gen.history_cutoff(30) == "2026-09-26"


def test_dst_fall_back_night_new_york_boundaries(frozen):
    ny = "America/New_York"
    # 2026-11-01 03:30 UTC is 2026-10-31 23:30 EDT in America/New_York (previous day)
    frozen(datetime(2026, 11, 1, 3, 30, tzinfo=UTC))
    assert timeutil.local_today(ny) == date(2026, 10, 31)

    # 2026-11-01 04:30 UTC is 2026-11-01 00:30 EDT in America/New_York (new day across midnight)
    frozen(datetime(2026, 11, 1, 4, 30, tzinfo=UTC))
    assert timeutil.local_today(ny) == date(2026, 11, 1)

