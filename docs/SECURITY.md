# Security (Zill & Shams)

Status: hardening pass of 2026-10-23. This describes controls that exist in the code. It is not a certification,
and no external penetration test has been done.

## 1. Threat model

**Data that exists.** The product stores no user data: no accounts, no database, no analytics cookies, no ads.
A user's location (or typed origin and destination) is sent per request, used to compute a route in memory and
discarded. Agent sessions live in process memory and vanish on restart. City data (OpenStreetMap buildings,
trees, graph) and precomputed shade tiles are public data baked offline.

**Secrets.** The LLM API key (OpenCode Go or Voke) exists only in the server `.env` (git-ignored) and is never
sent to the browser. `/api/health` reports provider and model, never the key.

| Threat | Impact | Control |
| --- | --- | --- |
| Bot hammering `/api/agent/*` | LLM spend, the only variable cost | tight per-IP token bucket, 1,000-char message cap, flat-rate LLM plan (see COSTS.md) |
| Hammering routing or `/api/shade/compute` | CPU exhaustion on a single-worker VM | per-IP buckets, tighter bucket on compute-heavy endpoints |
| Oversized or malformed bodies | memory, parser abuse | 64 KB body cap, 1,000-char string cap, strict Pydantic models |
| Other websites calling the API from a visitor's browser | abuse under a victim's IP | CORS allow-list (browser-enforced) |
| Clickjacking of the app | UI redress | `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` (except `/embed`) |
| Script injection | low impact (no sessions or accounts), still limited | CSP `default-src 'self'`, `object-src 'none'`, no third-party scripts |
| Location leakage through logs | privacy | log scrubbing (coordinates, keys, bearer tokens) |
| Stack traces and internals in errors | information disclosure | generic error bodies; detail only in server logs |

Out of scope today: volumetric DDoS beyond one VM (an upstream CDN or Caddy rate-limit module would be next),
multi-tenant isolation (no tenants yet), account takeover (no accounts).

## 2. Controls implemented

### API (`backend/zill/api/security.py`, installed in `api/main.py`)

- **Per-IP token buckets**, in memory, by tier (burst / sustained per minute): agent 8 / 10; heavy compute
  (`/api/shade/compute`, `/api/cities/build`) 3 / 2; routing (`/api/route`, `/api/departure`, `/api/plan`) 30 / 90;
  shade tiles and city files 300 / 1,800; everything else 60 / 240. `/api/health` is exempt (container
  healthcheck). Exceeding a bucket returns **429** with `Retry-After`. The agent tier is the tightest because it is
  the only path that can cost money.
- **Client IP.** `X-Forwarded-For` is read only when the TCP peer is a private, loopback or link-local address
  (Caddy on the Docker network). The last entry is used, because Caddy appends the real client there and earlier
  entries are client-controlled. A public peer's header is ignored.
- **Caps.** Request body at most 64 KB (413). Any JSON string at most 1,000 characters, agent message at most
  1,000 (422). Any query-string value (place query `q`, etc.) at most 200 characters (422).
- **CORS allow-list:** `https://zill.itshamza.me`, `https://zill.169-58-66-146.sslip.io`, and
  `http://localhost|127.0.0.1|[::1]:<port>` for development. Methods GET, POST, OPTIONS only.
- **Errors.** Typed generic bodies (`{"error": {"code", "message", "request_id"}}`). Unhandled exceptions return a
  fixed "Internal server error"; the traceback goes to the server log only.
- **Logs.** A log-record factory scrubs every record from every logger: `lat=`/`lon=`/`"latitude":` values, decimal
  coordinate pairs, `Bearer` tokens, `api_key=` values, `sk-` style keys, and the literal value of any
  `ZILL_*KEY/TOKEN/SECRET` environment variable. Tracebacks are not scrubbed, but they do not contain request bodies.
- **Response headers** on API responses: `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- **Tests:** `backend/tests/test_security.py` (16 tests: buckets and refill, 429 with Retry-After, XFF trust, caps,
  CORS allow and deny including look-alike origins, generic errors, log scrubbing).
- `ZILL_RATE_LIMIT=0` turns limiting off (load tests, local dev). Caps, CORS and headers stay on. The test suite
  sets it in `tests/conftest.py`.

### Web (`frontend/next.config.ts`)

Sent on every page. Verified with `next build && next start -p 3011` and headless Chromium:

- `Content-Security-Policy`: `default-src 'self'`; `script-src 'self' 'unsafe-inline'`; `style-src 'self' 'unsafe-inline'`;
  `img-src 'self' data: blob:`; `font-src 'self' data:`; `connect-src 'self' blob: data:`; `worker-src 'self' blob:`;
  `object-src 'none'`; `base-uri 'self'`; `form-action 'self'`; `frame-ancestors 'none'`.
  `'unsafe-eval'` is **not** allowed in production (only under `next dev`, for React refresh). `/film`, `/app` and
  `/embed/hotel` rendered with zero CSP violations in the production build. Script `'unsafe-inline'` remains
  because Next injects inline bootstrap scripts; removing it needs a per-request nonce middleware, which makes
  pages dynamic (listed under "next").
- `Strict-Transport-Security: max-age=31536000` (one year, no includeSubDomains, no preload; the apex hosts other apps).
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
- `Permissions-Policy: geolocation=(self)`; camera, microphone, payment, usb, interest-cohort disabled.
- `X-Frame-Options: DENY` everywhere **except** `/embed/*`, which uses `frame-ancestors *` so hotels can iframe the widget.
- Fonts are self-hosted; the production build makes no third-party requests.

`deploy/Caddyfile.snippet` adds `nosniff` and `Referrer-Policy` on `/api/*` and strips the `Server` header; TLS is
terminated by Caddy. The page headers come from Next itself.

## 3. Dependency audit (2026-10-23, real output)

- **Python** (`pip-audit` on the backend venv): *No known vulnerabilities found.* The local package `zill` is
  skipped because it is not on PyPI.
- **npm** (`npm audit --omit=dev` in `frontend/`): **2 vulnerabilities (1 moderate, 1 high)**, both via the PostCSS
  copy bundled inside `next` (advisories on `</style>` stringification and `sourceMappingURL` handling in CSS
  comments). Exposure is low here: PostCSS runs at build time on our own CSS, not on user input. The suggested fix is
  `next@16`, a breaking major upgrade, not done overnight. Re-audit when upgrading Next.

## 4. Privacy alignment (an aim, not a claim of compliance)

We aim to align with the UAE Federal PDPL (Decree-Law 45 of 2021) and the GDPR (relevant for the Oslo and EU
audience) by design: data minimisation (nothing stored), purpose limitation (location used only to compute the
requested route), no profiling, no third-party trackers, no ads. A legal review, a privacy notice page and a data
processing agreement template for B2B customers are `[TEAM TO FILL]` before any paid launch. Free text sent to the
LLM provider leaves our server; that provider is a processor and its terms must be reviewed.

## 5. What's next

1. External penetration test before B2B launch.
2. Auth for B2B dashboards, per-tenant API keys and quotas (today limits are per IP).
3. Nonce-based CSP (drop script `'unsafe-inline'`); upgrade Next to clear the PostCSS advisory.
4. Upstream rate limiting or bot protection at Caddy or a CDN; move buckets to a shared store if more than one API
   worker is ever run (the VM runs one, so in-memory is correct today).
5. Dependency scanning in CD (`pip-audit`, `npm audit`) and a privacy notice page.
