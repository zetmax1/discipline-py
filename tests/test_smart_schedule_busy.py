"""
F9a S5: the API sends `busy` (commitment segments of the chosen week, overnight ones split at
midnight) instead of the browser's commitments; the rest day gets no plan and focus is capped per
day (owner answer 1). The legacy `commitments` body keeps working until the contract step.
"""

import pytest
from pydantic import ValidationError

from app.smart_schedule.generator import ScheduleGenerator
from app.smart_schedule.schemas import SmartScheduleRequest
from tests.test_contract import load_contract
from tests.test_smart_schedule import MockDB, mins

GOALS = {"deepWorkHours": 15, "studyHours": 10, "restHours": 7}


def run(**body):
    body.setdefault("goals", GOALS)
    return ScheduleGenerator(MockDB(), 1, "Asia/Tashkent").generate(SmartScheduleRequest(**body))


def planned(resp, day):
    return [(mins(b.startTime), mins(b.endTime), b.category) for b in resp.blocks if b.day == day and b.category != "fixed"]


def overlaps(spans, lo, hi):
    return any(s < hi and e > lo for s, e, _ in spans)


SLEEP = [  # Mon–Fri 23:00–07:00, as the API expands it: evening on the start day, morning on the next
    {"day": d, "startMin": 1380, "endMin": 1440, "name": "Sleep", "kind": "rest"} for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
] + [
    {"day": d, "startMin": 0, "endMin": 420, "name": "Sleep", "kind": "rest"} for d in ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
]


def test_busy_segments_block_exactly_their_slots():
    # 80 h of deep work fills every free weekday slot from 06:00 to 22:00.
    resp = run(busy=SLEEP, goals={"deepWorkHours": 80, "studyHours": 0, "restHours": 0}, weekStart="2026-11-16")
    mon, tue = planned(resp, "Monday"), planned(resp, "Tuesday")
    assert not overlaps(mon, 1380, 1440)
    assert not overlaps(tue, 0, 420)
    assert overlaps(mon, 360, 420), "Monday 06:00–07:00 is free: Sunday is not a sleep day"
    fixed = sorted((b.day, b.startTime, b.endTime) for b in resp.blocks if b.category == "fixed" and b.day in ("Monday", "Tuesday"))
    assert fixed == [("Monday", "23:00", "24:00"), ("Tuesday", "00:00", "07:00"), ("Tuesday", "23:00", "24:00")]


def test_busy_xor_commitments():
    legacy = [{"id": "s", "name": "Sleep", "startTime": "23:00", "endTime": "07:00", "days": ["Monday"]}]
    with pytest.raises(ValidationError):
        SmartScheduleRequest(busy=SLEEP, commitments=legacy, goals=GOALS)
    with pytest.raises(ValidationError):
        SmartScheduleRequest(goals=GOALS)
    assert run(commitments=legacy).blocks  # the legacy path is unchanged


@pytest.mark.parametrize("bad", [
    {"day": "Monday", "startMin": 600, "endMin": 600, "name": "x", "kind": "rest"},
    {"day": "Monday", "startMin": 1440, "endMin": 1440, "name": "x", "kind": "rest"},
    {"day": "Funday", "startMin": 60, "endMin": 120, "name": "x", "kind": "rest"},
    {"day": "Monday", "startMin": 700, "endMin": 600, "name": "x", "kind": "rest"},  # the API splits overnight ones
])
def test_busy_segments_are_validated(bad):
    with pytest.raises(ValidationError):
        SmartScheduleRequest(busy=[bad], goals=GOALS)


def test_nothing_is_planned_on_the_rest_day():
    resp = run(busy=[], restDay=7, goals={"deepWorkHours": 30, "studyHours": 30, "restHours": 20})
    assert planned(resp, "Sunday") == []
    assert planned(resp, "Saturday"), "other days still get plans"


def test_focus_is_capped_per_day_and_the_rest_is_shortfall():
    resp = run(busy=[], maxFocusMinPerDay=120, goals={"deepWorkHours": 20, "studyHours": 0, "restHours": 0})
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        assert sum(e - s for s, e, c in planned(resp, day) if c == "deep-work") <= 120
    assert resp.placed_minutes["deep-work"] == 5 * 120  # deep work uses weekdays
    assert resp.shortfall_minutes["deep-work"] == 20 * 60 - 600


def test_v2_request_matches_the_contract_the_api_sends():
    schema = load_contract()["smart_schedule_request_v2"]
    required = set(schema["required"])
    assert required == {"weekStart", "busy", "goals", "restDay", "maxFocusMinPerDay"}
    body = {"weekStart": "2026-11-16", "busy": SLEEP, "goals": {"deepWorkHours": 12, "studyHours": 5.5, "restHours": 0},
            "restDay": 7, "maxFocusMinPerDay": 180}
    SmartScheduleRequest(**body)  # what the API sends is accepted as is
    assert set(schema["properties"]["busy"]["items"]["required"]) <= {"day", "startMin", "endMin", "name", "kind"}
