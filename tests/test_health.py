"""GET /health checks the database: 200 when reachable, 503 (without details) when not."""

import os

import pytest
from fastapi.testclient import TestClient

import main
from app import database


def test_health_ok_when_database_answers(monkeypatch):
    monkeypatch.setattr(database, "ping", lambda: None)
    r = TestClient(main.create_app()).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {"database": "ok"}}
    assert r.headers["cache-control"] == "no-store"


def test_health_503_without_details_when_database_is_down(monkeypatch):
    def down():
        raise RuntimeError("could not connect to server at db.railway.internal:5432")

    monkeypatch.setattr(database, "ping", down)
    r = TestClient(main.create_app()).get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "checks": {"database": "unavailable"}}
    assert "railway.internal" not in r.text


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
def test_ping_reaches_a_real_database(monkeypatch):
    monkeypatch.setattr(database, "engine", database.create_db_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgres://", "postgresql://", 1)))
    database.ping()
