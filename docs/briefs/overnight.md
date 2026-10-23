# Overnight pivot briefs: Zill & Shams (2026-10-23 night)

Read first, in order: `docs/briefs/common.md` (all 13 rules still apply), `CLAUDE.md`, `docs/PIVOT_PLAN.md`
(sections 2, 3, 6 and **8 are binding**), `docs/CONTRACTS.md`, then your stream section below.

## Extra rules for tonight (all streams)

- **Never touch `README.md`** (the user has uncommitted edits in it). Never commit; the orchestrator commits.
- **Never kill processes you did not start.** The user's dev server may be on :3000/:8000. Run your own servers on
  other ports (API :8010–8019, web :3010–3019) and stop them when done.
- The product is now **Zill & Shams** (ظل وشمس, "shade and sun"). Shade mode = least direct sun (today's
  behaviour). Sun mode = most direct sun / daylight, for well-being. Medical wording: *well-being, daylight*;
  vitamin D only as "a daylight / vitamin D window" indicator with "not medical advice". Never "treats".
- Real company names (Talabat, Deliveroo, Careem) only as *target customers*.
- No ads anywhere: monetisation is freemium + B2B subscriptions.
- Keep every existing test green. Add tests for everything you add. Python tests: `backend/tests/`.
- When you change an API, update `docs/CONTRACTS.md` (append a section "Overnight additions" with your part).
- Append to `docs/PROGRESS.md` and `docs/DECISIONS.md` as usual.

---

## Stream A — Sun mode, well-being, UV and clouds (engine + API)

Own: `backend/zill/routing/*`, `backend/zill/weather/*`, `backend/zill/api/routes_route.py`,
`backend/zill/api/schemas.py` (route/departure/plan parts only), `backend/zill/config.py` (new constants only),
new `backend/zill/wellbeing.py`, tests `backend/tests/test_sun_mode*.py`, `test_wellbeing*.py`.

1. **Preference.** Add `preference: Literal["shade","sun"] = "shade"` to `RouteRequest`, `DepartureRequest`,
   `PlanRequest` and to the planner/tdsp functions. Shade mode is unchanged byte-for-byte (existing tests and
   `data/scenarios/hero.json` must still reproduce).
2. **Sun cost without negative weights.** Sun mode minimises `t + λ·W·shade_time`, where shade_time = time spent
   *not* in direct sun on the edge (indoor/covered/ac_link count as shade). Keeps edge costs ≥ 0 so A* stays
   valid. λ triple stays [0,1,3]. Indoor links get no bonus in sun mode.
3. **Response.** Keep keys `fastest`, `balanced`, and the λ=3 route under `coolest` in shade mode. In sun mode
   the λ=3 route is under `sunniest` (no `coolest` key). Both modes add `best` (= coolest or sunniest) and
   top-level `preference`. Sun-mode stats add `sun_gained_s`, `sun_gained_pct` (vs fastest) while keeping all
   existing fields. Departure optimiser in sun mode maximises sun (min `shade_time + μ·wait`).
4. **Weather.** Extend Open-Meteo fetch with hourly `uv_index`, `cloud_cover`, `shortwave_radiation`
   (and `apparent_temperature` if missing). Keep the recorded-fallback path and label (`Recorded`/`Live`).
5. **`wellbeing.py`** (pure functions, unit-tested), returned in route responses as `wellbeing`:
   - `uv`: index + WHO band (low/moderate/high/very high/extreme) + advice text from WHO bands.
   - `heat_stress`: band from apparent temperature (use the existing heat model/RHL where possible; cite the
     band thresholds' source in a code comment; if no source, label "indicative").
   - `daylight_window`: `true` when sun altitude ≥ 45° (shadow shorter than your height) **and** UV ≥ 3 and
     cloud cover < 70%; text: "Daylight / vitamin D window. Well-being guidance, not medical advice." Also
     return sun altitude and "your shadow is N× your height" (1/tan(alt)).
   - `breaks`: hydration / shade-break prompts every N minutes of direct sun for long routes in hot conditions.
   - `overcast`: in sun mode when cloud cover ≥ 70%, say the sunny route has little direct sun today.
6. **Hero sun scenarios.** Extend `scenarios.py` search with a documented sun-mode search (Dubai winter morning,
   e.g. 2026-01-15 09:00–11:00, office-worker lunch walk; pick by the same honest procedure). Write
   them to `data/scenarios/hero.json` under a new key `sun` without changing the existing shade entries.
   Report real numbers only. Oslo sun scenarios come later (Stream D bakes Oslo; the orchestrator will ask you).
7. Gate: all backend tests green + new tests; ruff clean; a POST `/api/route` with `preference:"sun"` works via
   TestClient. Put the exact request/response shape in CONTRACTS.md.

## Stream B — Pluggable LLM provider (Voke + OpenCode Go) and the live agent

Own: `backend/zill/agent/llm.py`, `backend/zill/agent/backend.py`, `backend/zill/config.py` (LLM settings only),
`.env.example`, tests `backend/tests/test_llm*.py`, `docs/LLM.md` (new).

Facts verified from https://opencode.ai/docs/go/ (2026-10-23): OpenCode Go OpenAI Chat Completions endpoint is
`https://opencode.ai/inference/go/openai/v1/chat/completions` (so base URL `https://opencode.ai/inference/go/openai/v1`);
model list at `https://opencode.ai/inference/go/v1/models`. Chat-completions models include `kimi-k3`,
`kimi-k3.1-pro`, `glm-5.3`, `glm-5.3-flash`, `deepseek-v4-pro`, `deepseek-v4.1-flash` (DeepSeek needs the Global
region), `minimax-m3.1-flash`, `longcat-2.5-preview-free` (free). Clients should send their own User-Agent and a
stable `x-opencode-session` header per conversation. Auth: assume `Authorization: Bearer <key>` (OpenAI SDK
default); verify with a keyless request that the endpoint answers 401/403 (not 404).

1. Providers list from env: `ZILL_LLM_PROVIDERS=opencode,voke` (order = priority). Per provider:
   `ZILL_OPENCODE_API_KEY`, `ZILL_OPENCODE_BASE_URL` (default above), `ZILL_OPENCODE_MODEL` (default `kimi-k3`),
   `ZILL_OPENCODE_MODEL_FAST` (default `glm-5.3-flash`); `ZILL_VOKE_*` likewise (defaults = today's Voke values).
   Keep backward compatibility: existing `ZILL_LLM_BASE_URL`/`ZILL_LLM_API_KEY`/`ZILL_MODEL` still work as
   provider "voke" (or "custom").
2. Fallback: on connect errors, 5xx, 401/403, 429 or timeout, try the next provider (and each provider's model
   fallback list). Availability probe cached as today. `/api/health` reports which provider/model is live
   (never the key). Send `x-opencode-session` (the agent session id) to OpenCode.
3. Tool calling must work with these models: tolerate providers that return `reasoning_content`, empty
   `content`, tool args as strings, or no `tool_choice` support (retry without it).
4. If no key is present, behaviour is exactly today's (recorded replays, labelled). Tests with a fake HTTP
   server (respx or a local stub) for fallback order, 429 → next provider, header presence, key never logged.
5. `docs/LLM.md`: how to set keys locally and on the VM (`/home/hamza/zill/.env`, then `deploy/cd.sh --force`),
   which models, costs from the OpenCode page (Go $10/month, Go Plus $40/month; per-model monthly limits).
6. Do **not** re-record replays (no key tonight). Stream A will add `preference`; later the orchestrator may ask
   you to add a "daylight seeker" persona and sun-mode to the agent tools.

## Stream C — Security hardening, load test, cost sheet

Own: `backend/zill/api/main.py`, new `backend/zill/api/security.py`, `frontend/next.config.ts` (headers only),
new `frontend/src/middleware.ts` if needed, `deploy/Caddyfile.snippet` (headers only; do NOT touch the VM),
`docs/SECURITY.md`, `docs/COSTS.md`, `scripts/loadtest.py` (new), tests `backend/tests/test_security*.py`.

1. API: per-IP token-bucket rate limits (in-memory; read client IP from `X-Forwarded-For` only when the request
   comes from a private/Docker address, i.e. Caddy). Tighter limit on `/api/agent/*` (LLM cost) than on
   routing. 429 with `Retry-After`. Request body cap (64 KB), string-length caps on free-text fields (agent
   message ≤ 1,000 chars; place query ≤ 200). CORS: allow only `https://zill.itshamza.me`,
   `https://zill.169-58-66-146.sslip.io`, and localhost dev origins. Generic error bodies (no stack traces).
   Logs must never contain lat/lon of user requests or the API key; add a log filter + a test.
2. Web: security headers via Next `headers()`: CSP (self; fonts self-hosted; `connect-src 'self'`; allow
   `'unsafe-eval'` only if three/next really needs it in production, verify), HSTS (1 year, includeSubDomains
   no), `X-Content-Type-Options`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`
   (geolocation=(self) only), `X-Frame-Options: DENY` everywhere **except `/embed`** (which needs
   `frame-ancestors *`). Verify with `next build && next start -p 3011` and a Playwright smoke that /film and
   /app still render with zero CSP console errors.
3. `docs/SECURITY.md`: threat model (what data exists: none stored; location used only per request; no
   accounts; LLM key server-side), the controls above, dependency audit results (`pip-audit` /
   `npm audit --omit=dev` real output summary), UAE PDPL / GDPR *alignment as an aim*, what's next (pen-test,
   auth for B2B dashboards, per-tenant keys).
4. `scripts/loadtest.py` (httpx + asyncio, no new heavy deps): ramp concurrent virtual users hitting a realistic
   mix (city load, /api/route hero, /api/sun, departure). Run it **locally** against a production-mode API on
   :8010 (single uvicorn worker, like the VM) and report real p50/p95/throughput/errors per concurrency level.
   Also run a *gentle* read-only run against https://zill.itshamza.me (max 20 concurrent, ≤ 60 s) and record it.
   Label every result "local machine" or "live VM" clearly.
5. `docs/COSTS.md`: VPS cost `[TEAM TO FILL — Contabo plan price]`, LLM cost per agent conversation computed
   from measured token counts of the recorded replays (count tokens in `backend/replay/*.json` messages with a
   tokenizer approximation, state the method) × published per-token prices (OpenCode Go is a flat $10/$40
   subscription with monthly per-model limits: compute conversations per month under it), cost to add a city
   (measure: time the Dubai bake steps from logs or re-run the shade bake timing; open data is free), cost per
   1,000 users (from load-test capacity). Real numbers only; every assumption labelled.

## Stream D — Oslo, the second city

Own: `data/cities.json` (add an entry), `data/cities/oslo/**`, `backend/zill/data/*` and `backend/zill/shade/*`
(only generic fixes needed for high latitudes; never Dubai-specific code), `backend/zill/sun/*`, tests
`backend/tests/test_oslo*.py`, `test_low_sun*.py`.

1. Core bbox: central Oslo, roughly Oslo S / Bjørvika / Karl Johans gate / Aker Brygge / Akershus fortress, similar
   area to Dubai Downtown (about 2 × 1.5 km). Timezone `Europe/Oslo`. Pick the bbox from OSM landmarks and write
   it in DECISIONS.
2. Run the same city-agnostic bake (OSM → buildings, heights, graph, trees, POIs, GLB, shade, exposure) the
   project already uses (`make bake` / `scripts/zill.py bake` / `zill.data.bake` — read how Dubai was baked).
   Shade dates for Oslo: winter solstice (2026-12-21), March equinox, summer solstice, plus a mid-October date.
   Night/polar logic: steps with sun below the horizon must be flagged as night, not "all shade".
3. **Low sun angles.** At Oslo midwinter noon the sun is ~6.6° high: shadows are ~8.6× building height. Check the
   raymarch's maximum ray length / caster buffer (`config.CASTER_BUFFER_M`) is long enough or is scaled per
   altitude, and add tests: synthetic box of height h at altitude 6.6° casts a shadow of length h/tan(alt) ±
   one grid cell; altitude < 0 → night flag. Fix generically if broken.
4. Gate: the API serves `/api/cities` listing oslo as ready, `/api/route` works in Oslo for both preferences
   (once Stream A lands; until then shade mode), counts reported honestly in PROGRESS.md (buildings, edges,
   trees, POIs). Bake logs to `data/raw/logs/`. Keep the GLB under ~8 MB (same texture/size discipline).

## Stream E — Typed places: full name index + "from X to Y"

Own: new `backend/zill/places/` package (index build, search, parse, online fallback), new
`backend/zill/api/routes_places.py` (and the one-line router include in `backend/zill/api/main.py` — coordinate:
Stream C also edits main.py; add only the include line), `data/cities/*/places.json`, tests
`backend/tests/test_places*.py`.

1. Index builder: one Overpass query per city bbox for every named feature (buildings, amenities, shops,
   tourism, leisure, streets, metro/bus stops, squares, parks, malls, hotels), including `name:en` and `name:ar`
   / `name:no` alternates. Snap each to the walk graph (reuse the existing snapping/door logic). Write
   `places.json` (id, name, alt_names, kind, lat, lon, x, z, node). Dubai now; Oslo once
   `data/cities/oslo/graph.json` exists (poll for it; if Stream D hasn't finished when you are done, report it).
2. Search: accent- and case-insensitive, Arabic/Norwegian letters folded (å→a, ø→o, æ→ae), prefix + token +
   fuzzy (rapidfuzz is fine) ranking, kinds weighted (landmarks/stations above shops), ≤ 20 ms per query.
3. Parse one-line input: "from X to Y", "X to Y", "X → Y", "X - Y", Arabic "من X إلى Y", plus optional
   "at 15:30", "tomorrow 9am", "walk/cycle/scooter", "shade/sunny". Return `{origin, dest, depart_at?, mode?,
   preference?, confidence}` with candidate lists when ambiguous.
4. Online fallback (only when the local index has no good match): Nominatim search bounded to the city bbox
   (`viewbox` + `bounded=1`), User-Agent `Zill-hackathon-prototype/0.1` (no email), ≤ 1 request/second
   globally, 2 s timeout, cached; results labelled `source: "online"`. Must be disable-able
   (`ZILL_ONLINE_GEOCODE=0`) and tests must not hit the network.
5. API: `GET /api/places/search?city=&q=&limit=` and `POST /api/places/parse {city, text}`. Document both in
   CONTRACTS.md. Existing `/api/route` must accept a place id from the new index as `origin`/`dest`.

---

# Wave 2 (starts after streams A, D, E land on main)

## Stream F — The app: rename, Shade ⇄ Sun, well-being, typed places, city switch

Own: `frontend/src/brand.ts`, `backend/zill/brand.py`, `frontend/src/app-ui/**`, `frontend/src/state/**`,
`frontend/src/lib/**`, `frontend/src/three/**`, `frontend/src/app/**` except `app/(stage)/film`,
`frontend/src/components/**`, `frontend/src/design/tokens.ts` (additions only), frontend tests, Playwright
scripts under `frontend/scripts/` for the app. Do not edit `frontend/src/film/**` (Stream G).

1. **Rename** to Zill & Shams via the brand files (NAME "Zill & Shams", ARABIC "ظل وشمس", TAGLINE
   "Shade when you need it. Sun when you want it."). Replace hard-coded "Zill" product names across app/landing/
   metadata/embed/OG with the brand constants. Keep the `zill` package/repo/domain names.
2. **Shade ⇄ Sun toggle** in the app (a restrained segmented control in the palette: shade = `shade #22333A`,
   sun = `ember #D07A35`; no glow). Calls the API with `preference`; the third route is labelled "Coolest" or
   "Sunniest"; stats show "sun saved" vs "sun gained". Route colours stay on-palette.
3. **Well-being card** from the route response `wellbeing` (UV band, heat stress, daylight / vitamin D window
   with "not medical advice", shadow-length line, break prompts, overcast note). Weather source labelled
   Live/Recorded.
4. **Typed places**: the CommandBar accepts free text: search-as-you-type over `/api/places/search`, and a
   one-line "from X to Y [at 15:30] [sunny]" parsed by `/api/places/parse` that fills A, B, time, mode,
   preference in one go. Online results labelled "online". Keep keyboard flow (↑↓ Enter Esc).
5. **City switch** Dubai ⇄ Oslo (`/app?city=oslo`): the 3D scene loads the city's GLB/graph/shade by city id
   from `/api/cities`; camera framing from the city bbox; time bar uses the city timezone; night state when the
   sun is down (honest "the sun is below the horizon" message, not fake shade). Persona presets include a
   "daylight seeker" (sun mode).
6. QA loop (CLAUDE.md): Playwright stills of /app in both cities × both preferences, the well-being card, typed
   input, 375 px mobile; open them, critique, fix, re-capture twice. Save to `docs/qa/overnight-app/`
   (git-ignored if > 5 MB total; keep ≤ 8 best in `docs/qa/best/`). `npm run typecheck && npm run lint &&
   npm test` green; `next build` green.

## Stream G — The film: Zill & Shams

Own: `frontend/src/film/**`, `frontend/src/app/(stage)/film/**`, film QA/record scripts. Read-only:
`frontend/src/three/**` (Stream F owns it; it now supports a `city` id).

Update the deterministic film (every chapter a pure function of chapter-local t; no timers):
1. Rename everywhere (brand constants). Title card: "Zill & Shams", ظل وشمس, the new tagline.
2. New chapter "Two directions": the same street, shade route vs sun route, from the real API data baked into
   the film data (use `data/scenarios/hero.json` `sun` entries; never invented numbers).
3. New chapter "Winter in Oslo": the Oslo city at a low December sun (long shadows), the sunniest walk, with the
   honest note that low winter sun means daylight and mood, not vitamin D.
4. Business chapters updated to PIVOT_PLAN §4 and §8: who pays (incl. municipalities / city planners, schools,
   elderly care, events), freemium and no ads, privacy and security (no accounts, location never stored),
   accuracy and update frequency (shadows every 10 min, weather hourly, maps re-baked weekly), what it costs to
   run and how many users one server handles (numbers from `docs/COSTS.md` only), well-being (not medical
   advice).
5. Keep total length ≈ the current one (trim elsewhere), keep the scroll cue, slow scroll and flicker fixes.
6. QA loop: stills of every chapter at 3 moments, open and critique (CLAUDE.md checklist), twice. Run the
   flicker probe (`frontend/scripts/qa-flicker.ts`) on the new chapters. Then `make record` style backup video
   if the recorder still works. Typecheck/lint/tests green.

## Stream H — Decks: regenerate PDF and PowerPoint

Own: `docs/pitch/**`. Inputs: `docs/PIVOT_PLAN.md` §4 + §8, `docs/SECURITY.md`, `docs/COSTS.md`, `docs/LLM.md`,
`data/scenarios/hero.json` (shade + sun), Oslo counts in `docs/PROGRESS.md`, new stills from
`docs/qa/best/` and the film. Update `docs/pitch/GAMMA_PROMPT.md`, then rebuild
`docs/pitch/deck/index.html` → `Zill-and-Shams-pitch.pdf` (render.mjs) and `Zill-and-Shams-pitch.pptx` (with
speaker notes). New slides answering the mentors: security & privacy, accuracy & update frequency, well-being
(not medical advice), expanded scope (B2G planning analytics etc.), costs to run, how many users (market size
sourced + capacity measured), freemium, no ads, Oslo. 15–17 slides, same theme. Open every rendered slide image
and check: no overflow, no baked-in film UI text, legible, on-brand. Every number traceable to a doc or source.
