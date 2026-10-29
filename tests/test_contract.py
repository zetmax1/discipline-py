"""
F-06 contract: real analytics responses must match the shape the frontend reads.

The frontend owns the contract (discipline/src/contracts/analytics.ts) and commits
its JSON Schema to discipline/contracts/analytics.schema.json. This test calls the
real endpoints and validates every response against that file. It fails (it does
not skip) when the file is missing: check out both repos side by side, or point
ANALYTICS_CONTRACT at the schema file.
"""

import copy
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import main
from app import charts, reports, timeutil
from app.database import get_db
from app.metrics import Block
from tests.test_internal_auth import bearer, make_token

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path(os.getenv(
    "ANALYTICS_CONTRACT", REPO_ROOT.parent / "discipline" / "contracts" / "analytics.schema.json"))

TODAY = date(2026, 10, 29)
NOON_TASHKENT = datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc)


def load_contract() -> dict:
    if not CONTRACT_PATH.is_file():
        pytest.fail(f"frontend contract not found at {CONTRACT_PATH}; check out discipline/ next to "
                    "discipline-py/ or set ANALYTICS_CONTRACT")
    return json.loads(CONTRACT_PATH.read_text())


def blk(days_ago, start, end, category="deep-work", status="completed", distractions=0):
    return Block(day=TODAY - timedelta(days=days_ago), start=start, end=end,
                 category=category, status=status, distractions=distractions)


RICH = [blk(i, "09:00", "11:00", distractions=i % 3) for i in range(0, 12)] + [
    blk(1, "13:00", "14:00", category="study"),
    blk(2, "15:00", "16:00", category="admin", status="skipped"),
    blk(0, "20:00", "21:00", category="rest", status="pending"),
    blk(3, "10:00", "10:00"),                       # zero-duration completed block
]
SPARSE = [blk(1, "09:00", "10:00", status="pending")]

ENDPOINTS = [
    ("today", "/analytics/today"),
    ("period_report", "/analytics/weekly"),
    ("period_report", "/analytics/monthly"),
    ("focus_patterns", "/analytics/focus-patterns?days=7"),
    ("focus_patterns", "/analytics/focus-patterns?days=30"),
]


@pytest.fixture
def client_for(monkeypatch):
    monkeypatch.setattr(timeutil, "_utcnow", lambda: NOON_TASHKENT)
    charts.chart_cache.clear()
    main.app.dependency_overrides[get_db] = lambda: None

    def make(blocks):
        monkeypatch.setattr(reports, "load_blocks", lambda db, u, s, e: [b for b in blocks if s <= b.day <= e])
        main.app.dependency_overrides[get_db] = lambda: _NoHistoryDB()
        return TestClient(main.app)

    yield make
    main.app.dependency_overrides.clear()


class _NoHistoryDB:
    """Stands in for the session the schedule generator queries for history."""

    def query(self, *a, **k):
        return self

    filter = order_by = query

    def all(self):
        return []


def errors(schema: dict, payload) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in Draft202012Validator(schema).iter_errors(payload)]


@pytest.mark.parametrize("dataset", ["rich", "sparse", "empty"])
@pytest.mark.parametrize("key,path", ENDPOINTS)
def test_responses_match_frontend_contract(client_for, dataset, key, path):
    contract = load_contract()
    blocks = {"rich": RICH, "sparse": SPARSE, "empty": []}[dataset]
    r = client_for(blocks).get(path, headers=bearer(make_token()))
    assert r.status_code == 200, r.text
    problems = errors(contract[key], r.json())
    assert not problems, f"{path} ({dataset}) breaks the frontend contract:\n" + "\n".join(problems)


@pytest.mark.parametrize("goals", [
    {"deepWorkHours": 15, "studyHours": 10, "restHours": 7},
    {"deepWorkHours": 80, "studyHours": 80, "restHours": 80},   # forces shortfall
])
def test_smart_schedule_matches_frontend_contract(client_for, goals):
    contract = load_contract()
    body = {"commitments": [{"id": "s", "name": "Sleep", "startTime": "23:00", "endTime": "07:00",
                             "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}], "goals": goals}
    r = client_for(RICH).post("/analytics/smart-schedule", json=body, headers=bearer(make_token()))
    assert r.status_code == 200, r.text
    problems = errors(contract["smart_schedule"], r.json())
    assert not problems, "smart-schedule breaks the frontend contract:\n" + "\n".join(problems)


def test_contract_covers_patterns_both_ways(client_for):
    contract = load_contract()
    for blocks, expected in ((RICH, False), (SPARSE, True)):
        body = client_for(blocks).get("/analytics/weekly", headers=bearer(make_token())).json()
        assert body["patterns"]["insufficient_data"] is expected
        assert not errors(contract["period_report"], body)


def test_contract_rejects_a_renamed_field(client_for):
    """Guards the guard: dropping a field the UI reads must fail validation."""
    contract = load_contract()
    body = client_for(RICH).get("/analytics/weekly", headers=bearer(make_token())).json()
    broken = copy.deepcopy(body)
    broken["comparison"]["focus_score_diff"] = broken["comparison"].pop("change")
    assert errors(contract["period_report"], broken)
