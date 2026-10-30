"""Structured JSON logs with the request ID Gin sends in X-Request-ID."""

import io
import json
import logging
import re

from fastapi.testclient import TestClient

import main
from app import observability


def capture() -> io.StringIO:
    stream = io.StringIO()
    observability.setup_logging(stream)
    return stream


def lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def app_with_logging_route():
    app = main.create_app()

    @app.get("/_log")
    def _log():
        logging.getLogger("app.test").warning("inside the request")
        return {"ok": True}

    return app


def test_request_id_from_gin_is_echoed_and_logged():
    stream = capture()
    client = TestClient(app_with_logging_route())
    resp = client.get("/_log?user=secret-query", headers={"X-Request-ID": "gin-0123456789abcdef"})
    assert resp.headers["X-Request-ID"] == "gin-0123456789abcdef"
    records = lines(stream)
    inner = [r for r in records if r["msg"] == "inside the request"]
    access = [r for r in records if r["msg"] == "request"]
    assert inner and inner[0]["request_id"] == "gin-0123456789abcdef" and inner[0]["level"] == "WARNING"
    assert access and access[0]["request_id"] == "gin-0123456789abcdef"
    assert access[0]["method"] == "GET" and access[0]["path"] == "/_log" and access[0]["status"] == 200
    assert "duration_ms" in access[0]
    assert "secret-query" not in stream.getvalue(), "the query string must not be logged"


def test_missing_or_malformed_request_id_is_replaced():
    capture()
    client = TestClient(main.create_app())
    for header in ({}, {"X-Request-ID": "bad id\nwith newline"}, {"X-Request-ID": "x" * 200}):
        got = client.get("/", headers=header).headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{32}", got), got


def test_logs_outside_a_request_have_no_request_id():
    stream = capture()
    logging.getLogger("app.test").info("startup")
    record = lines(stream)[-1]
    assert record["msg"] == "startup" and "request_id" not in record


def test_exceptions_are_logged_as_one_json_line():
    stream = capture()
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("app.test").exception("failed")
    record = lines(stream)[-1]
    assert record["level"] == "ERROR" and "ValueError: boom" in record["exc_info"]
