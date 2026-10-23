"""Security layer: rate limits, caps, CORS, headers, log scrubbing."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zill.api import security
from zill.api.security import Limit, SecurityMiddleware, TokenBuckets, client_ip, scrub, tier_for


def make_app(limits: dict[str, Limit] | None = None, clock=None) -> tuple[TestClient, TokenBuckets]:
    app = FastAPI()
    kw = {"clock": clock} if clock else {}
    buckets = TokenBuckets(limits, **kw)

    @app.get("/api/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/echo")
    async def echo(body: dict) -> dict:
        return {"n": len(str(body))}

    @app.post("/api/agent/message")
    async def msg(body: dict) -> dict:
        return {"got": len(body.get("text", ""))}

    app.add_middleware(SecurityMiddleware, buckets=buckets)
    return TestClient(app), buckets


@pytest.fixture(autouse=True)
def _limits_on(monkeypatch):
    monkeypatch.setenv("ZILL_RATE_LIMIT", "1")


def test_tiers():
    assert tier_for("/api/health") is None
    assert tier_for("/api/agent/message") == "agent"
    assert tier_for("/api/shade/compute") == "heavy"
    assert tier_for("/api/route") == "route"
    assert tier_for("/api/shade/dubai_downtown/summer/1300.png") == "assets"
    assert tier_for("/api/sun") == "api"


def test_agent_limit_tighter_than_route():
    assert LIMITS_OK()


def LIMITS_OK() -> bool:
    return security.LIMITS["agent"].per_min < security.LIMITS["route"].per_min


def test_rate_limit_429_retry_after_and_refill():
    t = [0.0]
    c, _ = make_app({**security.LIMITS, "api": Limit(burst=3, per_min=60)}, clock=lambda: t[0])
    assert [c.get("/api/ping").status_code for _ in range(3)] == [200, 200, 200]
    r = c.get("/api/ping")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["code"] == "rate_limited"
    t[0] += 1.0  # 60/min = 1 token per second
    assert c.get("/api/ping").status_code == 200


def test_health_exempt():
    c, _ = make_app({**security.LIMITS, "api": Limit(burst=1, per_min=1)})
    for _ in range(10):
        assert c.get("/api/health").status_code == 200


def test_limit_off_switch(monkeypatch):
    monkeypatch.setenv("ZILL_RATE_LIMIT", "0")
    c, _ = make_app({**security.LIMITS, "api": Limit(burst=1, per_min=1)})
    for _ in range(5):
        assert c.get("/api/ping").status_code == 200


def test_ips_are_independent():
    c, b = make_app({**security.LIMITS, "api": Limit(burst=1, per_min=1)})
    assert b.take("1.1.1.1", "api")[0]
    assert not b.take("1.1.1.1", "api")[0]
    assert b.take("2.2.2.2", "api")[0]


def test_client_ip_trusts_xff_only_from_private_peer():
    def scope(peer, xff):
        return {"client": (peer, 1), "headers": [(b"x-forwarded-for", xff.encode())]}

    assert client_ip(scope("172.18.0.5", "9.9.9.9")) == "9.9.9.9"
    assert client_ip(scope("172.18.0.5", "6.6.6.6, 9.9.9.9")) == "9.9.9.9"  # last = appended by Caddy
    assert client_ip(scope("8.8.4.4", "9.9.9.9")) == "8.8.4.4"  # public peer: header ignored
    assert client_ip(scope("172.18.0.5", "not-an-ip")) == "172.18.0.5"


def test_body_cap_413():
    c, _ = make_app()
    big = "a" * 1000
    r = c.post("/api/echo", json={"x": [big] * 100})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_agent_message_cap():
    c, _ = make_app()
    assert c.post("/api/agent/message", json={"text": "x" * 1000}).status_code == 200
    r = c.post("/api/agent/message", json={"text": "x" * 1001})
    assert r.status_code == 422
    assert "1000" in r.json()["error"]["message"]


def test_any_long_string_rejected_and_normal_body_replayed():
    c, _ = make_app()
    assert c.post("/api/echo", json={"a": {"b": ["y" * 1001]}}).status_code == 422
    r = c.post("/api/echo", json={"a": "ok"})
    assert r.status_code == 200 and r.json()["n"] > 0  # body reached the handler intact


def test_query_value_cap():
    c, _ = make_app()
    assert c.get("/api/ping", params={"q": "a" * 200}).status_code == 200
    assert c.get("/api/ping", params={"q": "a" * 201}).status_code == 422


def test_response_headers():
    c, _ = make_app()
    r = c.get("/api/ping")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


# --- real app: CORS and generic errors -------------------------------------------------------------
@pytest.fixture(scope="module")
def real():
    from zill.api.main import app

    return TestClient(app, raise_server_exceptions=False)


def _preflight(c, origin):
    return c.options(
        "/api/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_cors_allow_list(real):
    for ok in (
        "https://zill.itshamza.me",
        "https://zill.169-58-66-146.sslip.io",
        "http://localhost:3000",
        "http://127.0.0.1:3011",
    ):
        assert _preflight(real, ok).headers.get("access-control-allow-origin") == ok
    for bad in ("https://evil.example", "https://zill.itshamza.me.evil.example", "http://localhost.evil.example:3000"):
        assert "access-control-allow-origin" not in _preflight(real, bad).headers


def test_generic_error_body(real):
    r = real.post("/api/route", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert "Traceback" not in r.text and "File \"" not in r.text
    r = real.get("/api/nope")
    assert r.status_code == 404 and "error" in r.json()


# --- log scrubbing -----------------------------------------------------------------------------------
def test_scrub_coordinates_and_keys(monkeypatch):
    monkeypatch.setenv("ZILL_OPENCODE_API_KEY", "supersecretkey123456")
    s = scrub('POST body {"lat": 25.19724, "lon": 55.27439} at 25.19724,55.27439 key=supersecretkey123456')
    assert "25.197" not in s and "55.274" not in s and "supersecretkey" not in s
    assert "Bearer [redacted]" == scrub("Bearer abcdefgh12345678")
    assert "sk-" not in scrub("token sk-abcdef123456789")
    assert scrub("rid=ab12 GET /api/sun -> 200 12ms") == "rid=ab12 GET /api/sun -> 200 12ms"


def test_log_records_are_scrubbed(caplog):
    security.install_log_scrubbing()
    log = logging.getLogger("zill.api")
    with caplog.at_level(logging.INFO, logger="zill.api"):
        log.info("route origin lat=%s lon=%s", 25.1972, 55.2744)
        log.info("auth Bearer %s", "abcdefghij123456")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "25.1972" not in text and "55.2744" not in text and "abcdefghij123456" not in text
    assert "[redacted]" in text
