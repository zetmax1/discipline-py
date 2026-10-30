"""Optional Sentry: off without a DSN; events carry the request ID and no secrets."""

import json

import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

import main
from app import errtrack


def app_that_fails():
    # Kept apart from the secrets below: Sentry ships a few source lines around the raise.
    app = main.create_app()

    @app.post("/_boom")
    def _boom():
        raise RuntimeError("boom")

    return app


class CaptureTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.events.append(json.loads(item.payload.get_bytes()))


SECRETS = ("query-secret", "body-secret", "header-secret", "cookie-secret")


def test_disabled_without_dsn():
    assert errtrack.init_sentry("", "test") is False


def test_unhandled_error_is_reported_with_request_id_and_scrubbed():
    transport = CaptureTransport()
    try:
        assert errtrack.init_sentry("https://public@o0.ingest.sentry.io/1", "test", transport=transport) is True
        client = TestClient(app_that_fails(), raise_server_exceptions=False)
        resp = client.post(f"/_boom?token={SECRETS[0]}", json={"password": SECRETS[1]},
                           headers={"Authorization": f"Bearer {SECRETS[2]}", "Cookie": f"s={SECRETS[3]}",
                                    "X-Request-ID": "gin-0123456789abcdef"})
        assert resp.status_code == 500
        sentry_sdk.flush()
        assert len(transport.events) == 1, "one event: the exception (the access line is not reported)"
        event = transport.events[0]
        assert event["tags"]["request_id"] == "gin-0123456789abcdef"
        assert event["environment"] == "test"
        dump = json.dumps(event)
        for secret in SECRETS:
            assert secret not in dump, secret
    finally:
        sentry_sdk.init(dsn=None)
