"""
F-06: typed responses for every endpoint; patterns/insights live in the period report
(the endpoint the Analytics page calls) and need 7 days with data in the trailing 30.
Clock: Thursday 2026-10-29 12:00 Tashkent.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import main
from app import reports, schemas, timeutil
from app.database import get_db
from app.metrics import Block
from tests.test_internal_auth import bearer, make_token

TZ = "Asia/Tashkent"
NOON_TASHKENT = datetime(2026, 10, 29, 7, 0, tzinfo=UTC)
TODAY = date(2026, 10, 29)


def day_block(days_ago, start="09:00", end="10:00", status="completed", category="deep-work"):
    return Block(day=TODAY - timedelta(days=days_ago), start=start, end=end, category=category, status=status)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(timeutil, "_utcnow", lambda: NOON_TASHKENT)


def use_blocks(monkeypatch, blocks):
    monkeypatch.setattr(reports, "load_blocks", lambda db, u, s, e: [x for x in blocks if s <= x.day <= e])


def test_fewer_than_7_days_reports_days_needed(monkeypatch):
    use_blocks(monkeypatch, [day_block(i) for i in (1, 2, 4)])
    p = reports.period_report(None, 1, TZ, "week")["patterns"]
    assert p == {"insufficient_data": True, "days_needed": 4, "days_with_data": 3, "window_days": 30}


def test_patterns_use_trailing_30_days_not_the_selected_range(monkeypatch):
    # 8 days with data, all before this week -> week view still has patterns
    use_blocks(monkeypatch, [day_block(i) for i in range(4, 12)] + [day_block(40)])
    p = reports.period_report(None, 1, TZ, "week")["patterns"]
    assert p["insufficient_data"] is False
    assert p["days_with_data"] == 8 and p["window_days"] == 30
    assert p["insights"]


def test_patterns_content(monkeypatch):
    blocks = []
    for i in range(1, 15):                               # two weeks of perfect 09:00-12:00 deep work
        blocks.append(day_block(i, "09:00", "12:00"))
    blocks.append(day_block(1, "13:00", "14:00", status="pending", category="study"))  # yesterday dips
    use_blocks(monkeypatch, blocks)
    p = reports.period_report(None, 1, TZ, "month")["patterns"]
    assert p["peak_hour"] == 9
    assert p["best_weekday"] in {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
    assert p["trend"] in {"improving", "stable", "declining"}
    assert 0 <= p["consistency_score"] <= 100


def test_every_route_declares_a_response_model():
    for route in main.app.routes:
        if isinstance(route, APIRoute):
            assert route.response_model is not None, f"{route.path} has no response_model"


@pytest.fixture
def client(monkeypatch):
    use_blocks(monkeypatch, [day_block(i) for i in range(9)])
    main.app.dependency_overrides[get_db] = lambda: None
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.mark.parametrize("path,model", [
    ("/analytics/today", schemas.TodayResponse),
    ("/analytics/weekly", schemas.PeriodReport),
    ("/analytics/monthly", schemas.PeriodReport),
    ("/analytics/focus-patterns?days=30", schemas.FocusPatternsResponse),
])
def test_responses_validate_against_models(client, path, model):
    r = client.get(path, headers=bearer(make_token()))
    assert r.status_code == 200, r.text
    model.model_validate(r.json())


def test_week_and_month_share_comparison_keys(client):
    keys = set()
    for path in ("/analytics/weekly", "/analytics/monthly"):
        keys.add(tuple(sorted(client.get(path, headers=bearer(make_token())).json()["comparison"])))
    assert keys == {("change", "previous_focus_score")}
