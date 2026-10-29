"""
F-16: ranges stop at today in the user's zone; the streak counts back from the
most recent finished day (yesterday). Clock: Thursday 2026-10-29 12:00 Tashkent.
Streak rule: a finished day counts at >= 70% completion, days with nothing
planned are skipped, a day below 70% ends the streak.
"""

from datetime import date, datetime, timezone

import pytest

from app import reports, timeutil
from app.metrics import Block

TZ = "Asia/Tashkent"
NOON_TASHKENT = datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc)


def b(day, start="09:00", end="10:00", category="deep-work", status="completed"):
    return Block(day=date.fromisoformat(day), start=start, end=end, category=category, status=status)


HISTORY = [
    b("2026-10-24"),                                      # Sat 100%  (before the break -> not reached)
    b("2026-10-25", status="pending"),                    # Sun 0%    -> breaks the streak
    b("2026-10-26"),                                      # Mon 100%  -> counts
    # Tue 27: nothing planned -> skipped
    b("2026-10-28"), b("2026-10-28", "10:00", "10:15", status="pending"),  # Wed 80% -> counts
    b("2026-10-29", "09:00", "10:00", status="pending"),  # Thu (today, unfinished) -> ignored
    b("2026-10-30", status="pending"),                    # Fri planned in the future
    b("2026-10-31", "09:00", "17:00", category="study"),  # Sat future block marked completed early
]


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(timeutil, "_utcnow", lambda: NOON_TASHKENT)
    queried = []

    def fake_load(db, user_id, start, end):
        queried.append((start, end))
        return [x for x in HISTORY if start <= x.day <= end]

    monkeypatch.setattr(reports, "load_blocks", fake_load)
    return queried


def test_week_range_is_clamped_to_today(setup):
    r = reports.period_report(None, 1, TZ, "week")
    assert r["start_date"] == "2026-10-26"
    assert r["end_date"] == "2026-10-29"              # clamped
    assert r["period_end_date"] == "2026-11-01"       # full week still reported
    assert [d["date"] for d in r["days"]] == ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]
    assert all(end <= date(2026, 10, 29) for _, end in setup)


def test_future_blocks_do_not_leak_into_totals(setup):
    r = reports.period_report(None, 1, TZ, "week")
    assert r["planned_minutes"] == 60 + 75 + 60      # Mon + Wed + today; nothing from Fri/Sat
    assert {c["category"] for c in r["category_minutes"]} == {"deep-work"}   # Sat's early 'completed' study excluded


def test_month_range_is_clamped_to_today(setup):
    r = reports.period_report(None, 1, TZ, "month")
    assert (r["start_date"], r["end_date"], r["period_end_date"]) == ("2026-10-01", "2026-10-29", "2026-10-31")
    assert r["days"][-1]["date"] == "2026-10-29"


def test_streak_counts_back_from_yesterday_skipping_empty_days(setup):
    # Wed 80% + Mon 100% (Tue empty, skipped); Sun 0% ends it. Today and the future are ignored.
    assert reports.period_report(None, 1, TZ, "week")["streak"] == 2
    assert reports.period_report(None, 1, TZ, "month")["streak"] == 2


def test_streak_is_zero_when_yesterday_was_below_threshold(monkeypatch):
    monkeypatch.setattr(reports, "load_blocks", lambda db, u, s, e: [
        x for x in [b("2026-10-27"), b("2026-10-28", status="skipped")] if s <= x.day <= e])
    assert reports.period_report(None, 1, TZ, "week")["streak"] == 0


def test_streak_with_no_history_is_zero(monkeypatch):
    monkeypatch.setattr(reports, "load_blocks", lambda *a: [])
    assert reports.period_report(None, 1, TZ, "week")["streak"] == 0
