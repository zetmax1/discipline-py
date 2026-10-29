import pytest
from fastapi.testclient import TestClient

import main
from app.config import load_settings

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_hidden_by_default(path):
    client = TestClient(main.create_app(enable_docs=False))
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_served_when_enabled(path):
    client = TestClient(main.create_app(enable_docs=True))
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("value,expected", [(None, False), ("false", False), ("1", False), ("true", True), ("TRUE", True)])
def test_enable_docs_setting(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("ENABLE_DOCS", raising=False)
    else:
        monkeypatch.setenv("ENABLE_DOCS", value)
    assert load_settings().ENABLE_DOCS is expected


def test_module_app_hides_docs_without_env():
    # conftest does not set ENABLE_DOCS, so the deployed app object must not expose docs.
    client = TestClient(main.app)
    for path in DOC_PATHS:
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost:8081"])
def test_no_cors_headers_for_any_origin(origin):
    client = TestClient(main.app)
    r = client.get("/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-credentials" not in r.headers


def test_cors_preflight_not_answered():
    client = TestClient(main.app)
    r = client.options(
        "/analytics/weekly",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers
    assert r.status_code != 200
