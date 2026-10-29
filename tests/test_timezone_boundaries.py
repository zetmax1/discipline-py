"""
F-05: today / week / month boundaries use the user's zone from the internal JWT.
The clock is frozen at Sunday 2026-10-25 19:30 UTC, which is already
Monday 2026-10-26 00:30 in Asia/Tashkent (UTC+5).
"""

from datetime import date, datetime, timezone

import pytest

from app import timeutil
from app.analytics.monthly_analysis import MonthlyAnalysis
from app.analytics.pattern_detection import PatternDetection
from app.analytics.weekly_analysis import WeeklyAnalysis
from app.services.focus_service import FocusService
from app.services.metrics_service import MetricsService
from app.services.productivity_service import ProductivityService
from app.smart_schedule.generator import ScheduleGenerator

TASHKENT = "Asia/Tashkent"
SUNDAY_1930_UTC = datetime(2026, 10, 25, 19, 30, tzinfo=timezone.utc)


@pytest.fixture
def frozen(monkeypatch):
    def freeze(instant):
        monkeypatch.setattr(timeutil, "_utcnow", lambda: instant)
    freeze(SUNDAY_1930_UTC)
    return freeze


@pytest.fixture
def ranges(monkeypatch):
    """Capture every (start, end) date range the services query."""
    seen = []

    def fake_load(db, user_id, start_date, end_date):
        seen.append((start_date, end_date))
        return MetricsService._tasks_to_dataframe([])

    monkeypatch.setattr(MetricsService, "load_tasks", staticmethod(fake_load))
    return seen


def test_half_past_midnight_tashkent_is_the_next_day(frozen):
    assert timeutil.local_today(TASHKENT) == date(2026, 10, 26)
    assert timeutil.local_today("UTC") == date(2026, 10, 25)


def test_weekly_report_uses_local_week(frozen, ranges):
    ProductivityService(db=None).weekly_report(1, tz=TASHKENT)
    assert ranges[0] == ("2026-10-26", "2026-11-01")   # this week starts Monday 26th locally
    assert ranges[1] == ("2026-10-19", "2026-10-25")   # previous week for comparison


def test_weekly_report_in_utc_is_still_previous_week(frozen, ranges):
    ProductivityService(db=None).weekly_report(1, tz="UTC")
    assert ranges[0] == ("2026-10-19", "2026-10-25")


def test_weekly_analysis_uses_local_week(frozen, ranges):
    WeeklyAnalysis(db=None).analyse(1, tz=TASHKENT)
    assert ranges[0] == ("2026-10-26", "2026-11-01")


def test_month_boundary_uses_local_month(frozen, ranges):
    frozen(datetime(2026, 10, 31, 19, 30, tzinfo=timezone.utc))  # 2026-11-01 00:30 Tashkent
    ProductivityService(db=None).monthly_report(1, tz=TASHKENT)
    MonthlyAnalysis(db=None).analyse(1, tz=TASHKENT)
    assert ranges[0] == ("2026-11-01", "2026-11-30")
    assert ranges[1] == ("2026-11-01", "2026-11-30")
    assert ranges[2] == ("2026-10-01", "2026-10-31")    # previous month comparison


def test_trailing_windows_end_on_local_today(frozen, ranges):
    FocusService(db=None).focus_patterns(1, days=7, tz=TASHKENT)
    PatternDetection(db=None).detect(1, days=7, tz=TASHKENT)
    trend = ProductivityService(db=None).productivity_trend(1, days=7, tz=TASHKENT)
    assert ranges[0] == ("2026-10-20", "2026-10-26")
    assert ranges[1] == ("2026-10-20", "2026-10-26")
    assert ranges[2] == ("2026-10-20", "2026-10-26")
    assert trend["trend"][-1]["date"] == "2026-10-26"


def test_schedule_history_cutoff_uses_local_date(frozen):
    gen = ScheduleGenerator(db=None, user_id=1, tz=TASHKENT)
    assert gen.history_cutoff(30) == "2026-09-26"
