"""
F-11: a chart with nothing to draw (zero total, no points, no score) returns a
placeholder image instead of raising, so one odd row can't 500 the Analytics page.
"""

import base64
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

import main
from app import charts, reports, timeutil
from app.database import get_db
from app.metrics import Block
from tests.test_internal_auth import bearer, make_token


@pytest.fixture(autouse=True)
def fresh_cache():
    charts.chart_cache.clear()


def png(b64):
    return base64.b64decode(b64)[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("points", [
    [],
    [{"label": "deep-work", "value": 0.0}],
    [{"label": "deep-work", "value": 0.0}, {"label": "study", "value": 0.0}],
])
def test_category_chart_with_zero_total_returns_placeholder(points):
    c = charts.category_chart(1, "weekly", "week", points)
    assert png(c["image"])
    assert c["image"] == charts.placeholder_image()
    assert c["data"] == points


def test_gauge_without_score_returns_placeholder():
    c = charts.gauge_chart(1, "weekly", "week", None)
    assert c["image"] == charts.placeholder_image() and c["data"] == {"score": None}


def test_trend_without_values_returns_placeholder():
    c = charts.trend_chart(1, "focus-patterns", 30, [{"label": "2026-10-28", "value": None}])
    assert c["image"] == charts.placeholder_image()


def test_real_data_is_not_a_placeholder():
    c = charts.category_chart(1, "weekly", "week", [{"label": "study", "value": 1.0}])
    assert png(c["image"]) and c["image"] != charts.placeholder_image()


def test_completed_zero_duration_task_does_not_500(monkeypatch):
    monkeypatch.setattr(timeutil, "_utcnow", lambda: datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc))
    zero = Block(day=date(2026, 10, 27), start="10:00", end="10:00", category="deep-work", status="completed")
    monkeypatch.setattr(reports, "load_blocks", lambda db, u, s, e: [zero] if s <= zero.day <= e else [])
    main.app.dependency_overrides[get_db] = lambda: None
    try:
        client = TestClient(main.app)
        for path in ("/analytics/weekly", "/analytics/monthly", "/analytics/focus-patterns?days=7", "/analytics/today"):
            r = client.get(path, headers=bearer(make_token()))
            assert r.status_code == 200, (path, r.text)
    finally:
        main.app.dependency_overrides.clear()
