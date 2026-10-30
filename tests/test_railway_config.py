"""railway.json is Railway's config-as-code (it overrides the dashboard): it must start
the same server as the Procfile and point the healthcheck at the real /health route."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app import database

ROOT = Path(__file__).resolve().parents[1]


def railway_deploy() -> dict:
    return json.loads((ROOT / "railway.json").read_text())["deploy"]


def test_start_command_matches_the_procfile():
    procfile = dict(line.split(": ", 1) for line in (ROOT / "Procfile").read_text().splitlines() if line)
    assert railway_deploy()["startCommand"] == procfile["web"]


def test_healthcheck_path_is_the_health_route(monkeypatch):
    monkeypatch.setattr(database, "ping", lambda: None)
    path = railway_deploy()["healthcheckPath"]
    assert path == "/health"
    assert TestClient(main.create_app()).get(path).status_code == 200
