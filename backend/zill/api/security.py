"""API hardening: per-IP token buckets, body/string caps, CORS origins, response headers, log scrubbing.

Pure ASGI middleware (no BaseHTTPMiddleware) so SSE streams are never buffered. Nothing here stores
user data: buckets are keyed by IP in process memory and expire with the process.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

# --- constants (one source of truth for the security layer) ---------------------------------------
MAX_BODY_BYTES = 64 * 1024
MAX_STRING_CHARS = 1_000  # any JSON string value
MAX_AGENT_MESSAGE_CHARS = 1_000
MAX_QUERY_VALUE_CHARS = 200  # any URL query-string value (place query `q`, etc.)
MAX_BUCKETS = 20_000  # memory guard: oldest idle buckets are dropped beyond this

ALLOWED_ORIGINS = [
    "https://zill.itshamza.me",
    "https://zill.169-58-66-146.sslip.io",
]
ALLOWED_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1|\[::1\]):\d{1,5}$"


@dataclass(frozen=True)
class Limit:
    burst: float  # bucket capacity (requests)
    per_min: float  # sustained refill (requests per minute)


# Buckets are per (client IP, tier). The agent tier is the tight one: each message can cost LLM tokens.
LIMITS: dict[str, Limit] = {
    "agent": Limit(burst=8, per_min=10),
    "heavy": Limit(burst=3, per_min=2),  # /api/shade/compute, /api/cities/build: CPU-bound
    "route": Limit(burst=30, per_min=90),  # routing, departure, plan
    "assets": Limit(burst=300, per_min=1800),  # shade PNGs, city files, meta (a scrub loads many)
    "api": Limit(burst=60, per_min=240),  # everything else
}

_HEAVY = ("/api/shade/compute", "/api/cities/build")
_ROUTE = ("/api/route", "/api/departure", "/api/plan")
_ASSETS = ("/api/shade/", "/api/cities")
_EXEMPT = ("/api/health",)


def enabled() -> bool:
    """`ZILL_RATE_LIMIT=0` switches limiting off (load tests, local dev); caps and headers stay on."""
    return os.environ.get("ZILL_RATE_LIMIT", "1").strip().lower() not in ("0", "false", "no", "off")


def tier_for(path: str) -> str | None:
    """Rate-limit tier for a request path (None = not limited)."""
    if path.startswith(_EXEMPT):
        return None
    if path.startswith("/api/agent"):
        return "agent"
    if path.startswith(_HEAVY):
        return "heavy"
    if path.startswith(_ROUTE):
        return "route"
    if path.startswith(_ASSETS):
        return "assets"
    return "api"


# --- token buckets ---------------------------------------------------------------------------------
class TokenBuckets:
    """In-memory token buckets keyed by (ip, tier). Thread-safe; injectable clock for tests."""

    def __init__(self, limits: dict[str, Limit] | None = None, clock=time.monotonic) -> None:  # type: ignore[no-untyped-def]
        self.limits = limits or LIMITS
        self._clock = clock
        self._b: dict[tuple[str, str], list[float]] = {}  # key -> [tokens, last_ts]
        self._lock = threading.Lock()

    def take(self, ip: str, tier: str) -> tuple[bool, float]:
        """Consume one token. Returns (allowed, retry_after_seconds)."""
        lim = self.limits[tier]
        rate = lim.per_min / 60.0
        now = self._clock()
        with self._lock:
            if len(self._b) >= MAX_BUCKETS:
                self._evict(now)
            tokens, last = self._b.get((ip, tier), (lim.burst, now))
            tokens = min(lim.burst, tokens + (now - last) * rate)
            if tokens >= 1.0:
                self._b[(ip, tier)] = [tokens - 1.0, now]
                return True, 0.0
            self._b[(ip, tier)] = [tokens, now]
            return False, (1.0 - tokens) / rate

    def _evict(self, now: float) -> None:
        # drop the idlest half; an attacker rotating IPs cannot grow memory without bound
        order = sorted(self._b.items(), key=lambda kv: kv[1][1])
        for key, _ in order[: len(order) // 2]:
            self._b.pop(key, None)


def _is_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def client_ip(scope: dict[str, Any]) -> str:
    """Peer address; `X-Forwarded-For` is honoured only when the peer is private (Caddy, Docker network).

    Caddy appends the real client as the last entry, so the last entry is the one we trust
    (earlier entries are client-supplied and spoofable).
    """
    peer = (scope.get("client") or ("unknown", 0))[0]
    if not _is_private(peer):
        return peer
    for k, v in scope.get("headers", []):
        if k == b"x-forwarded-for":
            parts = [p.strip() for p in v.decode("latin-1").split(",") if p.strip()]
            if parts:
                cand = parts[-1]
                try:
                    ipaddress.ip_address(cand)
                    return cand
                except ValueError:
                    return peer
    return peer


# --- errors ---------------------------------------------------------------------------------------
def _body(status: int, code: str, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message, "request_id": None}}).encode()


async def _send_error(  # type: ignore[no-untyped-def]
    send, status: int, code: str, message: str, extra: list[tuple[bytes, bytes]] | None = None
) -> None:
    body = _body(status, code, message)
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        *_SEC_HEADERS,
        *(extra or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


_SEC_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"cache-control", b"no-store"),
]


def _long_string(obj: Any, limit: int) -> str | None:
    """Return the JSON path of the first string longer than `limit`, else None."""
    stack: list[tuple[str, Any]] = [("$", obj)]
    while stack:
        path, cur = stack.pop()
        if isinstance(cur, str):
            if len(cur) > limit:
                return path
        elif isinstance(cur, dict):
            stack.extend((f"{path}.{k}", v) for k, v in cur.items())
        elif isinstance(cur, list):
            stack.extend((f"{path}[{i}]", v) for i, v in enumerate(cur))
    return None


# --- the middleware ---------------------------------------------------------------------------------
class SecurityMiddleware:
    def __init__(self, app, buckets: TokenBuckets | None = None) -> None:  # type: ignore[no-untyped-def]
        self.app = app
        self.buckets = buckets or TokenBuckets()

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path: str = scope["path"]
        method: str = scope["method"]
        if not path.startswith("/api") or method == "OPTIONS":
            return await self.app(scope, receive, send)

        # 1. rate limit
        if enabled():
            tier = tier_for(path)
            if tier is not None:
                ok, retry = self.buckets.take(client_ip(scope), tier)
                if not ok:
                    secs = max(1, int(retry + 0.999))
                    return await _send_error(
                        send, 429, "rate_limited", "Too many requests. Please slow down.",
                        [(b"retry-after", str(secs).encode())],
                    )

        # 2. query-string value cap
        qs = scope.get("query_string", b"").decode("latin-1")
        if qs:
            from urllib.parse import parse_qsl

            for _, v in parse_qsl(qs, keep_blank_values=True):
                if len(v) > MAX_QUERY_VALUE_CHARS:
                    return await _send_error(send, 422, "validation_error", "A query parameter is too long")

        # 3. body cap + string caps (buffered: bounded to 64 KB, then replayed to the app)
        if method in ("POST", "PUT", "PATCH"):
            for k, v in scope["headers"]:
                if k == b"content-length":
                    try:
                        if int(v) > MAX_BODY_BYTES:
                            return await _send_error(send, 413, "payload_too_large", "Request body too large")
                    except ValueError:
                        return await _send_error(send, 400, "bad_request", "Bad Content-Length")
            chunks: list[bytes] = []
            size = 0
            while True:
                msg = await receive()
                if msg["type"] == "http.disconnect":
                    return
                chunk = msg.get("body", b"")
                size += len(chunk)
                if size > MAX_BODY_BYTES:
                    return await _send_error(send, 413, "payload_too_large", "Request body too large")
                chunks.append(chunk)
                if not msg.get("more_body", False):
                    break
            raw = b"".join(chunks)
            if raw:
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = None  # let FastAPI produce its own validation error
                if data is not None:
                    if path == "/api/agent/message" and isinstance(data, dict):
                        t = data.get("text")
                        if isinstance(t, str) and len(t) > MAX_AGENT_MESSAGE_CHARS:
                            return await _send_error(
                                send, 422, "validation_error",
                                f"Message too long (max {MAX_AGENT_MESSAGE_CHARS} characters)",
                            )
                    if _long_string(data, MAX_STRING_CHARS) is not None:
                        return await _send_error(
                            send, 422, "validation_error",
                            f"A text field is too long (max {MAX_STRING_CHARS})",
                        )
            replayed = False
            orig_receive = receive

            async def replay():  # type: ignore[no-untyped-def]
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": raw, "more_body": False}
                return await orig_receive()

            receive = replay

        # 4. response headers on every API response
        async def send_wrapped(message):  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                have = {k for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in _SEC_HEADERS[:2] if k not in have]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_wrapped)


def install(app) -> None:  # type: ignore[no-untyped-def]
    """Install CORS (allow-list) and the security middleware. Call once, before `common.install`."""
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(SecurityMiddleware)
    app.add_middleware(  # outermost: 429/413 responses still carry CORS headers
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_origin_regex=ALLOWED_ORIGIN_REGEX,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )


# --- log scrubbing ----------------------------------------------------------------------------------
_COORD_KV = re.compile(r"""(?i)(["']?\b(?:lat|lon|lng|latitude|longitude)\b["']?\s*[:=]\s*)-?\d+(?:\.\d+)?""")
_COORD_PAIR = re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}")
_SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
]


def _secret_values() -> list[str]:
    out = []
    for k, v in os.environ.items():
        if k.startswith("ZILL_") and ("KEY" in k or "TOKEN" in k or "SECRET" in k) and len(v) >= 8:
            out.append(v)
    return out


def scrub(text: str) -> str:
    """Remove coordinates and API keys from a log line."""
    text = _COORD_KV.sub(lambda m: m.group(1) + "[redacted]", text)
    text = _COORD_PAIR.sub("[redacted-coords]", text)
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "[redacted]", text)
    for secret in _secret_values():
        text = text.replace(secret, "[redacted]")
    return text


_factory_installed = False


def install_log_scrubbing() -> None:
    """Wrap the log-record factory so every record (any logger, incl. uvicorn and httpx) is scrubbed."""
    global _factory_installed
    if _factory_installed:
        return
    _factory_installed = True
    old = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        rec = old(*args, **kwargs)
        try:
            msg = rec.getMessage()
            clean = scrub(msg)
            if clean != msg:
                rec.msg, rec.args = clean, None
        except Exception:  # never let logging hygiene break logging
            pass
        return rec

    logging.setLogRecordFactory(factory)
