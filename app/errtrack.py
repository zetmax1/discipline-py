"""
Optional error reporting to Sentry (SENTRY_DSN). Without a DSN nothing is sent.
Events carry the request ID and never request bodies, cookies, query strings or
credentials.
"""

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import ignore_logger

from app.observability import access_logger, request_id_var

# The only request headers an event may carry.
_KEPT_HEADERS = {"user-agent", "content-type", "x-request-id"}


def _scrub(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = request["url"].split("?", 1)[0]
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() in _KEPT_HEADERS}
    event.pop("user", None)
    request_id = request_id_var.get()
    if request_id:
        event.setdefault("tags", {})["request_id"] = request_id
    return event


def init_sentry(dsn: str, environment: str, transport: Any = None) -> bool:
    """Start Sentry if dsn is set; returns whether it did."""
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment or None,
        send_default_pii=False,
        max_request_body_size="never",
        # Frame locals include the raw ASGI scope (query string, Authorization header).
        include_local_variables=False,
        before_send=_scrub,
        transport=transport,
    )
    # A 5xx access line is logged at ERROR; the exception itself is the event.
    ignore_logger(access_logger.name)
    return True
