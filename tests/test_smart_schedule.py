"""
F-08 (minimal): validated input, 30-minute precision, exact goal placement with
shortfall reporting, truthful reasoning, median preferred start, nothing before 06:00
or past midnight.
"""

import pytest
from fastapi.testclient import TestClient

import main
from app.database import get_db
from app.smart_schedule.generator import ScheduleGenerator
from app.smart_schedule.schemas import SmartScheduleRequest
from tests.test_internal_auth import bearer, make_token

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAYS = DAYS[:5]


class MockTask:
    def __init__(self, category, start_time):
        self.category = category
        self.start_time = start_time
        self.status = "completed"


class MockDB:
    """Returns the given completed tasks for any history query."""

    def __init__(self, tasks=()):
        self.tasks = list(tasks)

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return self.tasks


def generate(commitments=(), goals=None, history=()):
    req = SmartScheduleRequest(commitments=list(commitments),
                               goals=goals or {"deepWorkHours": 15, "studyHours": 10, "restHours": 7})
    return ScheduleGenerator(MockDB(history), 1, "Asia/Tashkent").generate(req)


def mins(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m


def placed(resp, category):
    return sum(mins(b.endTime) - mins(b.startTime) for b in resp.blocks if b.category == category)


def commitment(start, end, days=DAYS, name="Busy"):
    return {"id": "c", "name": name, "startTime": start, "endTime": end, "days": days}


# ------------------------------------------------------------------ #
#  Validation: 422 with a clear message, never 500
# ------------------------------------------------------------------ #

@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[get_db] = lambda: MockDB()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def post(client, body):
    return client.post("/analytics/smart-schedule", json=body, headers=bearer(make_token()))


GOOD = {"commitments": [commitment("23:00", "07:00")], "goals": {"deepWorkHours": 15, "studyHours": 10, "restHours": 7}}


@pytest.mark.parametrize("change,field", [
    ({"startTime": "9am"}, "startTime"),
    ({"startTime": "9:00"}, "startTime"),
    ({"endTime": "24:30"}, "endTime"),
    ({"endTime": "25:00"}, "endTime"),
    ({"startTime": "", "endTime": "10:00"}, "startTime"),
    ({"startTime": "10:00", "endTime": "10:00"}, "endTime"),
    ({"days": ["monday"]}, "days"),
    ({"days": []}, "days"),
    ({"days": ["Monday", "Monday"]}, "days"),
    ({"name": ""}, "name"),
])
def test_bad_commitments_get_422_with_field_message(client, change, field):
    body = {**GOOD, "commitments": [{**GOOD["commitments"][0], **change}]}
    r = post(client, body)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert f"commitments[0].{field}" in err


@pytest.mark.parametrize("value", ["-1", "80.5", "81", "0.3", "1e309", '"lots"', "NaN", "null"])
def test_bad_goals_get_422(client, value):
    # raw JSON text so out-of-range literals like 1e309 / NaN reach the server unchanged
    body = f'{{"commitments": [], "goals": {{"deepWorkHours": 15, "studyHours": {value}, "restHours": 7}}}}'
    r = client.post("/analytics/smart-schedule", content=body,
                    headers={**bearer(make_token()), "Content-Type": "application/json"})
    assert r.status_code == 422, r.text
    assert "goals.studyHours" in r.json()["error"]


@pytest.mark.parametrize("value", [0, 0.5, 4.5, 80])
def test_goal_bounds_and_half_hour_steps_accepted(client, value):
    r = post(client, {**GOOD, "goals": {**GOOD["goals"], "deepWorkHours": value}})
    assert r.status_code == 200, r.text


def test_24_00_end_is_valid(client):
    r = post(client, {**GOOD, "commitments": [commitment("22:00", "24:00")]})
    assert r.status_code == 200, r.text


def test_missing_goals_is_422_not_500(client):
    r = post(client, {"commitments": []})
    assert r.status_code == 422 and "goals" in r.json()["error"]


# ------------------------------------------------------------------ #
#  Exact placement and shortfall
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("goals", [
    {"deepWorkHours": 15, "studyHours": 10, "restHours": 7},
    {"deepWorkHours": 4.5, "studyHours": 0.5, "restHours": 3},
    {"deepWorkHours": 0, "studyHours": 0, "restHours": 0},
    {"deepWorkHours": 9, "studyHours": 13.5, "restHours": 10.5},
])
def test_places_exactly_the_requested_hours(goals):
    resp = generate([commitment("23:00", "07:00")], goals)
    assert placed(resp, "deep-work") == goals["deepWorkHours"] * 60
    assert placed(resp, "study") == goals["studyHours"] * 60
    assert placed(resp, "rest") == goals["restHours"] * 60
    assert resp.shortfall_minutes == {"deep-work": 0, "study": 0, "rest": 0}


def test_reports_shortfall_when_the_week_is_full():
    # Busy 06:00-20:00 every day leaves 2h per weekday (20:00-22:00) for deep work.
    resp = generate([commitment("06:00", "20:00")], {"deepWorkHours": 20, "studyHours": 0, "restHours": 0})
    assert placed(resp, "deep-work") == 600
    assert resp.shortfall_minutes["deep-work"] == 600
    assert any("10 h of Deep Work" in r for r in resp.reasoning)


def test_nothing_is_scheduled_over_a_0900_0945_commitment():
    resp = generate([commitment("09:00", "09:45", days=["Monday"], name="Meeting")],
                    {"deepWorkHours": 10, "studyHours": 5, "restHours": 7})
    for b in resp.blocks:
        if b.day == "Monday" and b.category != "fixed":
            assert mins(b.endTime) <= 9 * 60 or mins(b.startTime) >= 9 * 60 + 45, b


def test_no_block_overlaps_any_commitment():
    commitments = [commitment("23:00", "07:00"), commitment("10:00", "13:00", ["Monday", "Wednesday", "Friday"]),
                   commitment("17:00", "18:30", ["Monday", "Wednesday", "Friday"])]
    resp = generate(commitments, {"deepWorkHours": 20, "studyHours": 15, "restHours": 10})
    fixed = [b for b in resp.blocks if b.category == "fixed"]
    for b in resp.blocks:
        if b.category == "fixed":
            continue
        for f in (x for x in fixed if x.day == b.day):
            s, e = mins(f.startTime), mins(f.endTime)
            spans = [(s, e)] if s < e else [(s, 1440), (0, e)]
            for fs, fe in spans:
                assert mins(b.endTime) <= fs or mins(b.startTime) >= fe, (b, f)


def test_no_blocks_before_0600_or_past_midnight():
    history = [MockTask("rest", "05:00")] * 10       # learned preference before 06:00
    resp = generate([], {"deepWorkHours": 40, "studyHours": 30, "restHours": 40}, history)
    for b in resp.blocks:
        assert mins(b.startTime) >= 6 * 60, b
        assert mins(b.endTime) <= 24 * 60 and mins(b.endTime) > mins(b.startTime), b
        assert mins(b.startTime) % 30 == 0 and mins(b.endTime) % 30 == 0, b


def test_category_days_follow_existing_pattern():
    resp = generate([], {"deepWorkHours": 10, "studyHours": 9, "restHours": 7})
    assert {b.day for b in resp.blocks if b.category == "deep-work"} <= set(WEEKDAYS)
    assert {b.day for b in resp.blocks if b.category == "rest"} == set(DAYS)


def test_output_is_deterministic():
    a = generate([commitment("23:00", "07:00")])
    b = generate([commitment("23:00", "07:00")])
    key = lambda r: [(x.day, x.category, x.startTime, x.endTime) for x in r.blocks]
    assert key(a) == key(b)


# ------------------------------------------------------------------ #
#  Truthful reasoning and median preference
# ------------------------------------------------------------------ #

def test_default_placement_without_enough_history():
    resp = generate(history=[MockTask("deep-work", "08:00")] * 9)
    text = " ".join(resp.reasoning)
    assert "Deep Work: Default placement — not enough history yet" in text
    assert "learned from your history" not in text.split("Deep Work:")[1].split(".")[0]


def test_learned_from_history_with_ten_completed_blocks_uses_median():
    # median start 08:00 (mean would be 09:00)
    history = [MockTask("deep-work", "08:00")] * 6 + [MockTask("deep-work", "10:30")] * 4
    resp = generate(history=history, goals={"deepWorkHours": 5, "studyHours": 0, "restHours": 0})
    assert any(r.startswith("Deep Work: learned from your history") for r in resp.reasoning)
    assert any("08:00" in r for r in resp.reasoning if r.startswith("Deep Work"))
    monday = sorted(b.startTime for b in resp.blocks if b.day == "Monday" and b.category == "deep-work")
    assert monday[0] == "08:00"


def test_other_categories_say_default_when_only_one_has_history():
    history = [MockTask("deep-work", "08:00")] * 10
    text = generate(history=history).reasoning
    assert any(r.startswith("Study: Default placement — not enough history yet") for r in text)
    assert any(r.startswith("Rest: Default placement — not enough history yet") for r in text)
