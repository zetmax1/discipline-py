"""
Structured JSON logs carrying the request ID that the Go API sends in X-Request-ID,
so one request can be followed across both services.
"""

import json
import logging
import re
import secrets
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TextIO

import sentry_sdk
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,128}")
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

access_logger = logging.getLogger("app.access")


class JSONFormatter(logging.Formatter):
    """One JSON object per line: time, level, msg, logger, request_id, extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        request_id = request_id_var.get()
        if request_id:
            out["request_id"] = request_id
        out.update(getattr(record, "fields", {}))
        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging(stream: TextIO = sys.stdout) -> None:
    """Send every log record, uvicorn's included, as JSON to stream."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # RequestIDMiddleware writes the access line (with request_id, without the query string).
    logging.getLogger("uvicorn.access").disabled = True
    # HTTP client libraries log full URLs (query strings included) at INFO.
    for name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


class RequestIDMiddleware:
    """Keeps a well-formed incoming X-Request-ID or creates one, echoes it, logs access."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode(), b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else secrets.token_hex(16)
        token = request_id_var.set(request_id)
        # Sentry captures unhandled errors outside this middleware, after the
        # context variable is reset, so tag its per-request scope as well.
        sentry_sdk.get_isolation_scope().set_tag("request_id", request_id)
        status = 500
        start = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (REQUEST_ID_HEADER.encode(), request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            access_logger.log(
                logging.ERROR if status >= 500 else logging.INFO, "request",
                extra={"fields": {
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 3),
                }})
            request_id_var.reset(token)
