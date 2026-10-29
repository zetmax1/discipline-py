"""
F-03: the analytics service identifies the user only from Gin's internal JWT.
"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

import main
from app.api import analytics_api
from app.database import get_db
from app.smart_schedule import router as schedule_router
from app.smart_schedule.schemas import SmartScheduleResponse
from tests.conftest import TEST_ENV

SECRET = TEST_ENV["INTERNAL_JWT_SECRET"]
AUDIENCE = "discipline-py"

SCHEDULE_BODY = {
    "commitments": [],
    "goals": {"deepWorkHours": 5, "studyHours": 5, "restHours": 7},
}


def make_token(sub="7", aud=AUDIENCE, exp_in=60, secret=SECRET, alg="HS256", **extra):
    now = int(time.time())
    claims = {"iat": now, **extra}
    if sub is not None:
        claims["sub"] = sub
    if aud is not None:
        claims["aud"] = aud
    if exp_in is not None:
        claims["exp"] = now + exp_in
    return jwt.encode(claims, secret, algorithm=alg)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seen():
    """Records the user_id each endpoint's service layer was called with."""
    return []


@pytest.fixture
def client(monkeypatch, seen):
    class FakeGenerator:
        def __init__(self, db, user_id):
            seen.append(user_id)

        def generate(self, request):
            return SmartScheduleResponse(blocks=[], reasoning=[])

    class FakeFocusService:
        def __init__(self, db):
            pass

        def focus_patterns(self, user_id, days=30):
            seen.append(user_id)
            return {
                "heatmap_data": {},
                "productivity_by_weekday": [],
                "deep_work_distribution": [],
                "distraction_trend": [],
            }

    monkeypatch.setattr(schedule_router, "ScheduleGenerator", FakeGenerator)
    monkeypatch.setattr(analytics_api, "FocusService", FakeFocusService)
    for chart in ("focus_heatmap", "deep_work_distribution", "distraction_trend"):
        monkeypatch.setattr(analytics_api, chart, lambda *a, **k: "")
    monkeypatch.setattr(analytics_api.charts, "productivity_by_weekday", lambda *a, **k: "")

    main.app.dependency_overrides[get_db] = lambda: None
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


PROTECTED = [
    ("get", "/analytics/weekly", None),
    ("get", "/analytics/monthly", None),
    ("get", "/analytics/productivity-trend", None),
    ("get", "/analytics/focus-patterns", None),
    ("post", "/analytics/smart-schedule", SCHEDULE_BODY),
]


def call(client, method, path, body=None, headers=None, params=None):
    return client.request(method, path, json=body, headers=headers or {}, params=params)


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_missing_token_rejected(client, method, path, body):
    assert call(client, method, path, body).status_code == 401


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_old_api_key_alone_rejected(client, method, path, body):
    r = call(client, method, path, body, headers={"X-API-Key": "anything"}, params={"user_id": 1})
    assert r.status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(make_token(exp_in=-5), id="expired"),
        pytest.param(make_token(aud="someone-else"), id="wrong-aud"),
        pytest.param(make_token(aud=None), id="missing-aud"),
        pytest.param(make_token(exp_in=None), id="missing-exp"),
        pytest.param(make_token(sub=None), id="missing-sub"),
        pytest.param(make_token(sub="abc"), id="non-integer-sub"),
        pytest.param(make_token(sub="0"), id="zero-sub"),
        pytest.param(make_token(secret="x" * 40), id="wrong-secret"),
        pytest.param(make_token(alg="HS512"), id="wrong-alg"),
        pytest.param(
            jwt.encode({"sub": "7", "aud": AUDIENCE, "exp": int(time.time()) + 60}, None, algorithm="none"),
            id="alg-none",
        ),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_invalid_tokens_rejected(client, seen, method, path, body, token):
    r = call(client, method, path, body, headers=bearer(token))
    assert r.status_code == 401
    assert seen == []


def test_smart_schedule_uses_token_user_and_ignores_query(client, seen):
    r = call(
        client, "post", "/analytics/smart-schedule", SCHEDULE_BODY,
        headers=bearer(make_token(sub="7")), params={"user_id": 999},
    )
    assert r.status_code == 200, r.text
    assert seen == [7]


def test_focus_patterns_uses_token_user_and_ignores_query(client, seen):
    r = call(
        client, "get", "/analytics/focus-patterns",
        headers=bearer(make_token(sub="7")), params={"user_id": 999, "days": 14},
    )
    assert r.status_code == 200, r.text
    assert seen == [7]


def test_user_id_query_param_not_in_openapi_contract():
    for route in main.app.routes:
        for param in getattr(getattr(route, "dependant", None), "query_params", []):
            assert param.name != "user_id", f"{route.path} still accepts user_id"
