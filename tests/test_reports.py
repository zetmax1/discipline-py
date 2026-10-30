"""
F-07: every endpoint's numbers come from app.metrics.day_metrics.
Clock: Thursday 2026-10-29 12:00 in Asia/Tashkent.
"""

from datetime import UTC, date, datetime

import pytest

from app import reports, timeutil
from app.metrics import Block

TZ = "Asia/Tashkent"
NOON_TASHKENT = datetime(2026, 10, 29, 7, 0, tzinfo=UTC)


def b(day, start, end, category="deep-work", status="completed", distractions=0):
    return Block(day=date.fromisoformat(day), start=start, end=end, category=category, status=status, distractions=distractions)


# Monday: the 73-point fixture; Tuesday: empty; Wednesday: all pending (0); Thursday (today): 88-point fixture.
BLOCKS = [
    b("2026-10-26", "09:00", "11:00", distractions=2),
    b("2026-10-26", "11:00", "12:00", category="study"),
    b("2026-10-26", "13:00", "14:00", category="admin", status="skipped"),
    b("2026-10-28", "09:00", "10:00", status="pending"),
    b("2026-10-29", "09:00", "10:00"),
    b("2026-10-29", "10:00", "12:00", category="study", status="pending"),
    b("2026-10-29", "14:00", "15:00", distractions=1),
]
# Previous week: one day scoring 100 (3h deep work, no distractions, everything done).
PREVIOUS = [b("2026-10-20", "08:00", "11:00")]


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(timeutil, "_utcnow", lambda: NOON_TASHKENT)


@pytest.fixture
def data(monkeypatch):
    def fake_load(db, user_id, start, end):
        return [x for x in BLOCKS + PREVIOUS if start <= x.day <= end]
    monkeypatch.setattr(reports, "load_blocks", fake_load)


def test_today_report_matches_metrics_module(data):
    t = reports.today_report(None, 1, TZ)
    # at 12:00 the 10:00-12:00 study block is due: completion 60/180
    assert t["date"] == "2026-10-29"
    assert t["due_planned_minutes"] == 180 and t["due_completed_minutes"] == 60
    assert t["planned_minutes"] == 240 and t["completed_minutes"] == 120
    assert t["focus_score"] == round(100 * (0.5 * (60 / 180) + 0.3 * (120 / 180) + 0.2 * 0.875))
    assert t["daily_deep_work_target_minutes"] == 180


def test_week_score_is_mean_of_existing_daily_scores(data):
    r = reports.period_report(None, 1, TZ, "week")
    by_day = {d["date"]: d for d in r["days"]}
    assert by_day["2026-10-26"]["focus_score"] == 73
    assert by_day["2026-10-27"]["focus_score"] is None     # empty day excluded
    assert by_day["2026-10-28"]["focus_score"] == 0         # all pending counts as 0
    today_score = by_day["2026-10-29"]["focus_score"]
    assert r["focus_score"] == round((73 + 0 + today_score) / 3, 1)


def test_week_comparison_keys(data):
    r = reports.period_report(None, 1, TZ, "week")
    assert r["comparison"]["previous_focus_score"] == 100
    assert r["comparison"]["change"] == round(r["focus_score"] - 100, 1)


def test_week_totals_and_categories(data):
    r = reports.period_report(None, 1, TZ, "week")
    cats = {c["category"]: c["minutes"] for c in r["category_minutes"]}
    assert cats == {"deep-work": 240, "study": 60}
    assert r["deep_work_minutes"] == 240


def test_no_data_means_null_scores(monkeypatch):
    monkeypatch.setattr(reports, "load_blocks", lambda *a: [])
    r = reports.period_report(None, 1, TZ, "month")
    assert r["focus_score"] is None
    assert r["comparison"] == {"previous_focus_score": None, "change": None}
    assert reports.today_report(None, 1, TZ)["focus_score"] is None
