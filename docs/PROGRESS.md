# PROGRESS.md — running log

## 2026-10-22 22:40 · Phase 0 starting
- Read PRD.md + CLAUDE.md. Git repo initialised locally (no remote yet). GNU make installed.
- Wrote `docs/CONTRACTS.md` (shared data/API formats + file ownership) and `docs/DECISIONS.md`.
- LLM: OpenAI-compatible Voke endpoint; API key not yet present → agent will be built with replay/scripted fallback until `.env` has a key.
- Next: Phase 0 scaffold (sub-agent), then parallel streams: data bake, shade engine, routing, agent, 3D scene.

## 2026-10-22 22:45 · Phase 0 scaffold
- Backend skeleton (config, brand, geo, /api/health, /api/config), Next 15 frontend (routes /film /app /health /embed/hotel, tokens, fonts), scripts/zill.py, Makefile, docs stubs.
- Gate: make setup OK; pytest 4 passed; vitest 3 passed; typecheck/lint/build clean; demo served /film and proxied /api/health; Playwright smoke 1 passed; ports freed.

## 2026-10-22 · AGENT stream (Phase 5) — code complete, awaiting baked Dubai + hero.json for the shipped recordings
- `backend/zill/agent/`: llm (OpenAI-compatible client, FakeLLM), tokens (resolver + numeric guard), tools (14 tools), verifier (deterministic + LLM), orchestrator (Planner -> Verifier -> Narrator), monitor (sim clock, delay/closure/heat replans, L1/L2/L3, undo), personas, prompts, policy (UAE_OUTDOOR_WORK, unverified), scripted planner, narration templates, replay; `api/routes_agent.py`; `scripts/record_replay.py`.
- Tests: tokens 34 (incl. 240-case fuzz), llm 13, tools 12, orchestrator/monitor 26, replay+API 9(+1 skip), real-engine (synth city) 4. Known: shipped recordings need the baked city/hero.json (see report).

## 2026-10-22 · ROUTING + API stream (Phases 3-4) — code complete on synthetic fixture; real-data gate pending bake
- `services.py` (CityContext, CSR graph, SunTable), `routing/{modes,heat,graph,suntable,tdsp,departure,planner,scenarios,bench}.py`, `weather/*` (+ recorded files in `data/weather_cache/`), `api/{common,sse,schemas,routes_cities,routes_route,routes_misc}.py`.
- Tests: 58 passing (synthetic city `backend/tests/fixtures/synth_city`, built by `tests/synth.py`); real-data invariant test auto-runs once `data/cities/dubai_downtown` has graph + exposure.
- Synthetic-scale benchmark (16.9k nodes / 33.5k edges): route lam=3 p50 18 ms, p95 34 ms; compare triple p95 85 ms; departure (19) 0.36 s.
- Pending on real data: `python -m zill.routing.bench`, `python -m zill.routing.scenarios` (writes data/scenarios/hero.json).

### 2026-10-23 01:10 — SHADE stream (Phase 2) complete
- Exists: `zill/sun/{position,golden}.py`, `zill/shade/{heightmap,raymarch,exposure,cache,bake,explain,qa,bench,synthetic}.py`; `data/curated/sun_golden.json` (20 pvlib samples).
- Real bake (dubai_downtown, caster 2283×2412, core 1483×1612 @2 m, 8,460 buildings + 744 trees): winter 71 / spring 83 / summer 88 / hackathon 74 steps; PNG 29.5 MB total, npz ~1.0 MB; `building_mask.png`; `shade/bake_log.json`.
- Step time on the real grid (24 cores, numba, kernel only): mean 0.72 s, max 1.08 s (gate 2.5 s). With PNG write and a concurrent DATA bake: mean 1.55–1.90 s/step.
- Tests: 28 green (`tests/test_sun.py`, `test_shade_raymarch.py`, `test_shade_pipeline.py`); ruff clean.
- QA previews in `docs/qa/phase2/` checked: noon shadows fall N, 08:00 WNW, 16:00 ENE, summer 13:30 short shadows E; Burj Khalifa at origin.
- Graph changed? `python -m zill.shade.bake --city dubai_downtown --exposure-only` (~20 s) rebuilds exposure_*.npz from the PNGs.

## 2026-10-23 DATA stream (Phase 1)
- `python -m zill.data.bake --city dubai_downtown` writes meta / buildings (.json + .glb) / trees / graph / links / pois / glb_report from cached Overpass responses (~8 s; first fetch took ~21 min because Overpass was overloaded).
- Counts: 8,602 buildings (3,039 scene), 744 trees, 7,657 edges (7,029 walk), 15 ac_link + 116 covered + 1,446 indoor edges, 50 POIs, Burj 828 m.
- Tests: 28 green (`test_geo.py`, `test_data_heights.py`, `test_data_synthetic.py`, `test_data_dubai.py`); ruff clean.
- Known issues: edges below the 10k PRD gate (real OSM density); 79 % fallback heights; sparse trees. graph.json and buildings.json changed after SHADE's first run, so shade and exposure need a re-run.

## 2026-10-23 01:15 · Orchestrator checkpoint (Phases 1–5)
- Phase 1 data: committed + tagged. 3,039 scene buildings, Burj 828 m, 7,657 edges (gate >10k missed honestly — real OSM, see DECISIONS), Metro↔Dubai Mall AC link from OSM.
- Phase 2 shade: committed + tagged. 28 tests, 0.72 s/step, 4 presets force re-baked on final footprints. QA previews show correct shadow direction.
- Phase 3/4 routing+API: code committed, 60 tests. Real route p95 38 ms, departure 19×: 0.27 s. Hero scenario search being refined (POI quality + duration filters) — previous pick was a 59-min walk.
- Phase 5 agent: committed, 219 backend tests total. 4 SCRIPTED recordings (no LLM key yet), validated against hero.json.
- In flight: hero refinement + re-record (routing stream), 3D scene + /app (scene stream). Next: Film ch1–7.
- Known: sub-agents were paused ~1 h by a usage limit (23:40–00:40).

## 2026-10-23 · SCENE stream (Phase 6) — 3D scene core + /app basics
- One persistent `<Canvas>` in `src/app/(stage)/layout.tsx` shared by /film and /app. `src/three/`: Scene, World, CityBuildings (stone shader: id-hash tint, roofs, window lines, ground AO, dusk tungsten windows), ShadeGround (+ShadeDriver: two-step raster blend, +-3 prefetch, soft edges, fade-in, UV per CONTRACTS 2), Roads, Links, Trees (instanced), Routes (analysis ramp / presentation slate-brass + pulse, x-ray pass, traveller), Markers, Sky (+fog), SunLight (texel-snapped shadow box), lighting.ts (time-of-day keys), post/ (N8AO high, bloom, AgX, custom grade+vignette+grain), rigs/ (orbit/dolly/crane/fly/time + seeded float), CameraDriver, AppDrivers (time-lapse, fly-through), Perf (fps/p95/draw calls, auto-downgrade, context loss, `window.__zillReady`).
- `src/state/` (useCity, useSun, useRoute, useStage, useRig), `src/lib/` (sun, color/OKLab, api, assets, graph, routeGeom, format), `src/app-ui/` (CommandBar, JourneyPanel, TimeBar, FlyHud, AgentPanel slot, LoadingScreen, DebugOverlay, StageShell).
- Tests: vitest 49 passed (sun vs pvlib goldens <0.5 deg, geo goldens, rig determinism, FlyRig bank <= 4 deg, ramp, graph snap, routeGeom, lighting); typecheck, lint, `next build` green; Playwright `scene-app.spec.ts` + `smoke.spec.ts` pass on real data.
- Perf (RTX 4070 laptop, 1080p, ANGLE D3D11, vsync off, time scrubbing): high 114 fps (mean 8.8 ms, p95 12.2 ms, ~160 draw calls), medium 125 fps (p95 11.2), low 140 fps (p95 10.1). `docs/qa/phase6/perf.json`.
- Visual QA (`scripts/qa-capture.ts`, GPU via ANGLE D3D11): iter0 (synthetic fixture) -> ACES->AgX, desaturated sun keys, teal shade made visible, darker plinth, hydration fix, found routes hidden behind towers -> x-ray pass + depth lift + steeper route framing. iter1 (real Dubai) -> camera presets re-composed, plinth melts into haze, window lines stronger, ground albedo down. iter2 -> warmer stone, more sky fill on shaded facades, shade less saturated, thicker routes, restrained dusk windows + blue-umber night fill, softer indoor grade, HUD badge legibility. Alignment: hackathon 12:00 shadows fall N, 16:00 fall ENE, raster edges start at building bases, shadow-map faces agree (iter2/08, 09).
- Known: dusk (18:30 hackathon) still window-heavy and very dark; golden hour strongly amber; dark horizon band behind street-level shot; dev fixture deleted (generator kept at scripts/qa-make-fixture.ts).

## 2026-10-23 · OPS + DOCS stream (Phase 9 tooling, Phase 10 docs)
- Tooling: `scripts/zill.py` gains `record` (build, servers, stills, film video, app video), `deck`, `freshclone`; `frontend/scripts/{record-common,record-film,record-app,export-deck-assets,render-svg}.ts`; `imageio-ffmpeg` added to backend deps. Smoke-tested on the current build: 3 stills (02, 06 x3, 07) and a 30 s film video + mp4, ~100 s app video (agent steps verified separately on a stable page; the dev server's HMR reloaded the page during one run). Scratch outputs deleted. `freshclone` only guard-tested (ports were occupied).
- Docs: ARCHITECTURE (+ `docs/deck_assets/architecture.svg/png`), VALIDATION, RUNBOOK_DEMO, SPEAKER_NOTES (format read by `sync-film-data.mjs`), OPEN_ITEMS (grouped), README.
- Tests refreshed with `python scripts/zill.py test`: backend 221 passed, frontend 69 passed, typecheck + lint clean (data/test_results.json, 2026-10-23 01:51). Routing bench: `docs/qa/phase9/bench_routing.json` (route p95 25.1 ms, triple p95 68.8 ms, departure 19x 38.3 ms).
- Known: film not final, so deck stills and backup videos must be regenerated (`python scripts/zill.py record`); no in-browser stills fallback viewer confirmed; scripted agent sessions not live.

## 2026-10-23 APP stream
- Built: shared `ActivityFeed` (src/app-ui/feed), agent panel (chat, SSE feed, route cards, approval, autonomy L1-3, persona, simulated events, replan diff + undo), planner / fleet / crew views (`/app?view=`), `/embed/hotel`, `/health`, SSE client + streaming proxy route handlers (`src/app/api/agent/*`, needed because Next's rewrite proxy gzips and buffers SSE).
- Tests: vitest 69 passing; Playwright app-agent 2 passing. QA stills: docs/qa/app/iter1..iter3.
- Known: no LLM key, so all sessions are "Scripted session (live model not connected)"; replay supports only the recorded delay simulation; undo in replay is a local view revert. Route ribbon not visible in q=low swiftshader stills (scene stream).

## 2026-10-23 07:55 · FILM stream (Phases 7–8, film part) — all 12 chapters built, QA'd
- `frontend/src/film/`: master.ts (12 chapters, 780 s, pure `evaluate(t, data)` with camera/sun blends and ink dips), chapters/ch01–ch12, data.ts (FilmData loader: API + `public/film-data`), Overlay.tsx + panels/ + charts/DepartureChart.tsx, FilmPage.tsx (Lenis scroll ↔ t, keys, autoplay, presenter strip, `?qa=1&t=`, `__zillFilmSetT`, `__zillChapters`, `__zillFrameReady`), three/FilmWorld (single frame loop, split view), three/FilmExtras (grid, road draw, sun arc, sun rays, travellers, 3D labels), three/Globe, StillsFallback (PRD 17.4).
- Shared scene: additive film hooks only (see DECISIONS 2026-10-23 film); `/app` smoke (`e2e/scene-app.spec.ts`) still green.
- Tests: vitest 74/74 (film master: 780 s sum, determinism, monotonic chapters, ≤ 2 text overlays, Ch.2 counter = hero.json); Playwright `e2e/film.spec.ts` 2/2 (load + Space + chapter jumps; full autoplay at 40× with no console errors) + smoke.
- Visual QA: phase7 iter0→iter2 (ch1–7: sunrise recomposed west→east, POV street shot, plinth/edge hidden, film look, scrims/panels for legibility, steeper street, split view shows only Fastest | Coolest), phase8 iter1→iter2 (ch8–12: replan panel, compact feed, globe size/labels, golden-hour framing).
- Perf (RTX 4070 laptop, ANGLE D3D11, 1080p, high): p95 ch4 5.9 ms, ch5 5.9 ms, ch6 feed 10.3 ms, ch6 fly 6.7 ms, ch6 split 7.7 ms (`docs/qa/phase8/perf.json`).
- Known: Ch.5 street labels sit in a tower cluster (readable but towers crowd the frame); Ch.4 build reveal + Ch.11 globe are stylised; AC-link card has no dedicated camera move onto the link interior.
- 2026-10-23 DATA follow-up: entrance links + entrance-aware POI snapping; graph now 7,659 edges (indices changed again, exposure re-run with `--exposure-only`, shapes 7659×steps). Burj Khalifa → Dubai Mall walk = 447 m indoor. Full backend suite 222 passed.

## 2026-10-23 08:05 · Orchestrator checkpoint (Phases 6–8 green)
- Phase 6 scene + /app: tagged. Route-ribbon NaN-alpha bug (invisible on SwiftShader) found via APP QA and fixed.
- APP: agent panel (streamed feed, approvals, L1–L3, simulated replan), planner, fleet, crew, hotel embed, /health — committed.
- Phase 7–8 Film: all 12 chapters, 780 s, deterministic; vitest 74, film e2e full autoplay with no console errors; p95 frame ≤ 10.3 ms on RTX 4070 (ch4–6). Tagged phase-7/8-green.
- Ops/docs: record/deck/freshclone tooling, architecture diagram, VALIDATION, RUNBOOK, SPEAKER_NOTES, OPEN_ITEMS — committed.
- Repo hygiene: per-iteration QA images (phase7/8) git-ignored; best stills in docs/qa/best/. Note: phase6 + app QA images (~116 MB) are already in history.
- In flight: Dubai Mall entrance connectivity fix (data) → then exposure/hero/replay regeneration; film polish round (ch7 chart legibility, ch2 framing, grade).
- Next: regenerate hero + replays, `scripts/zill.py record` (stills + backup videos), freshclone test, final docs refresh.
- For the humans: add `ZILL_LLM_API_KEY` to `.env` then run `backend/.venv/Scripts/python.exe scripts/record_replay.py --live` to replace scripted sessions with live ones. A stray file `D:\tmp_bench.txt` (bench log) was left outside the repo — safe to delete.

## 2026-10-23 09:05 · FINAL SUMMARY (Phases 0–10 green; Phase 11 / P2 skipped)

**What exists**
- Engine on real OSM Downtown Dubai: 8,602 shadow-casting buildings (3,039 rendered), Burj 828 m, 7,659-edge walk/cycle graph, OSM Metro↔Dubai Mall AC link, linked mall entrances, 744 mapped trees, 50 POIs.
- Sun (pvlib) + numba shadow raymarch (0.72 s/step), shade rasters for 4 preset dates, per-edge exposure; time-dependent A* (triple p95 < 70 ms), departure optimiser, planner, honest hero search.
- Agent: Planner → tools → Verifier → Narrator with token-resolved numbers (240-case fuzz), Monitor with L1–L3 autonomy and undo, replay. Sessions are SCRIPTED (no LLM key yet) and badged so.
- Film `/film`: 12 chapters, 780 s, deterministic, scroll + autoplay + presenter mode + stills fallback; opens on a dim skyline with a "Scroll to begin" cue (160 px of scroll per film second).
- App `/app`: time bar, A→B routing, Fastest/Balanced/Coolest, analysis view, fly-through, agent panel, planner, fleet, crew, `/embed/hotel`, `/health`.
- Tests: backend 222 passed, frontend 74 passed (`data/test_results.json`). Fresh-clone test PASS (clone → setup → demo → 6 Playwright specs).
- Deck: 14 stills in `docs/deck_assets/stills/`, `architecture.svg/png`. Backup videos `backup_film.mp4` (13:11, 1080p) and `backup_app_demo.mp4` (1:19) exist LOCALLY only (git-ignored, too large).

**What's cut / not done**
- Phase 11 (P2): extra cities, Ch.4 city morph, procedural Burj, fountain shader — skipped (Ch.4 shows the pipeline card, Ch.11 marks other cities "roadmap").
- Live LLM sessions: no key yet. Phase-1 gate "edges > 10,000" missed honestly (real OSM: 7,659).

**Start command**
`python scripts/zill.py demo` (or `make demo` with GNU make) → http://localhost:3000/film (waits for backend warm-up). Pre-flight: http://localhost:3000/health.

**Top 5 risks for the presenters**
1. Agent sessions are scripted, not live, until a key is added — the UI says so; be ready to explain (the tool calls and numbers are real engine output).
2. 79% of building heights are fallback estimates (OSM lacks height tags) — shade is a model estimate; say so if probed.
3. Departure optimiser says "leave now" for the hero trip (honest result) — present it as the agent checking and confirming, not as a saving.
4. Unverified on site: Metro↔Mall AC link, 2 curated mall-entrance links, UAE midday-break policy dates — all labelled "verify".
5. GPU/projector: run `/health` first; `L` toggles low quality; if WebGL fails the film falls back to stills; backup videos are in `docs/deck_assets/` on this laptop only.

**What the humans must do** — see `docs/OPEN_ITEMS.md`. Key items: add `ZILL_LLM_API_KEY` to `.env` and run `backend/.venv/Scripts/python.exe scripts/record_replay.py --live`; re-record hackathon-day weather; fill `[TEAM TO FILL]` market/pricing items; field-test readings for Ch.10; confirm slot length; delete stray `D:\tmp_bench.txt` (safety check blocked automated removal).

## 2026-10-23 night - Stream B (LLM providers)
Pluggable provider chain (OpenCode Go + Voke) in `agent/llm.py`, config in `config.py`, `.env.example`, `docs/LLM.md`.
Tests: `tests/test_llm_providers.py` (stub HTTP servers, real openai SDK): fallback order, 401/403/429/5xx/connect, model walk,
tool_choice retry, reasoning/think handling, session + UA headers, no key in logs/errors/status. Full backend suite 263 passed; ruff clean.
Not done: no live call (no key); replays not re-recorded. Open: routes_agent should call `get_llm().for_session(session.id)`.

## 2026-10-23 night - Stream E (typed places)
New `backend/zill/places/` (fold, build, index, parse, online, service) + `api/routes_places.py` (`GET /api/places/search`, `GET /api/places/stats`, `POST /api/places/parse`). Dubai `data/cities/dubai_downtown/places.json`: 1,066 places (amenity 203, building 267, food 223, shop 165, hotel 41, stop 43, street 64, landmark 25, park 15, mall 7, station 8, square 5), 11 dropped as > 150 m from the walk graph. Search 6-8 ms per query on the real index (local machine). `/api/route` accepts index ids and online ids.
Tests: `tests/test_places.py` 30 passed; ruff clean. Full suite: 305 passed, 1 failed (`test_smoke.py::test_health`, caused by Stream B's health payload change, not places).
Oslo index: not built yet (`data/cities/oslo/graph.json` did not exist when Stream E finished). Run `python -m zill.places.build oslo` after the Oslo bake.
Known limits: Arabic names exist only where OSM has `name:ar`, so Arabic transliterations of English names do not match; the online fallback was only exercised against a fake transport (no network in tests).

## 2026-10-23 night - Stream A (sun mode, well-being, UV and clouds)
`preference: shade|sun` through tdsp/compare/departure/planner and `/api/route|departure|plan`; new `zill/wellbeing.py`
(WHO UV bands, indicative heat stress, daylight / vitamin D window with shadow ratio, break prompts, overcast note) returned as
`wellbeing`; weather adds hourly cloud cover + shortwave radiation; sun hero search writes `hero.json["sun"]`.
Shade mode verified identical: all 3 hero scenarios + the departure table recomputed equal to hero.json.
Sun hero (real, Dubai 2026-01-15, 8,190 jobs, 2,289 eligible): winter_morning_walk Address Sky View → The Dubai Mall 10:00:
fastest 1,204 s with 214 s direct sun; sunniest 1,347 s with 851 s sun (+637 s, +299 %) for +143 s. office_lunch_walk Burj Park →
Boulevard Plaza 12:30: 847 s/314 s sun vs 908 s/689 s sun (+375 s, +119 %) for +61 s. Both clear-sky geometry; the recorded
weather says 97 % / 100 % cloud cover and the sun is below 45° (31.4°, 43.7°), so the daylight window is closed and the overcast note shows.
Tests: `test_sun_mode.py` 14 + `test_wellbeing.py` 30 = 44 new; full backend suite 351 passed; ruff clean on Stream A files.
Known issues: ERA5 total cloud cover includes thin high cloud (632 W/m² shortwave at "100 %" on 2026-01-15 12:30), so `overcast` may
overstate; a clear spring/hackathon-date sun scenario could be added; frontend does not yet show sun mode / wellbeing.

## 2026-10-23 night — Stream C (security, load test, costs)
Exists: `backend/zill/api/security.py` (token buckets, XFF only from private peers, 64 KB / 1,000 / 200 caps, CORS allow-list, log scrubbing),
wired in `api/main.py`; `tests/test_security.py` (16) + `tests/conftest.py` (rate limit off by default in tests); security headers in
`frontend/next.config.ts` (CSP, HSTS, nosniff, Referrer-Policy, Permissions-Policy, X-Frame-Options except /embed); `deploy/Caddyfile.snippet` API headers
(not deployed); `docs/SECURITY.md`, `docs/COSTS.md`, `scripts/loadtest.py`.
Results: full backend suite green at last run (238 passed before other streams' tests landed), ruff clean. Production build: /film, /app, /embed/hotel render with
0 CSP violations. pip-audit clean; npm audit 2 findings (PostCSS inside next, fix = next 16).
Load (local, 1 worker, no limiter): peak ~26 req/s at 20 users, p95 596 ms; 40 users p95 2.6 s. Live VM (20 users max, 48 s): 16.9 req/s, p95 1.6 s, 0 errors.
Known issues: script-src still needs 'unsafe-inline' (Next bootstrap); Caddy/API changes take effect only after deploy; Next dev server sets its own CSP with unsafe-eval.

## 2026-10-23 night - Stream A follow-up (sky state, spring scenario, agent sun mode)
Overcast now uses the measured / Haurwitz clear-sky radiation index (< 0.4), with cloud cover only as fallback. Recorded Dubai 2026-01-15
has 97–100 % cloud cover but an index of 0.89–0.92, so both winter scenarios are no longer flagged overcast. Their notes now say only that the
sun is below 45° (31.4° and 43.7°). New `spring_daylight_walk` (2026-04-15, 3,640 jobs, 967 eligible; all four late-morning departures had an
open window): Business Bay Metro Station → Burj Park 10:30, fastest 1,435 s with 1,101 s direct sun, sunniest 1,704 s with 1,625 s
(+524 s, +48 %) for +269 s. Daylight window open (sun 59.9°, shadow 0.58× height, clear-sky index 0.91). The UV index of 8.7 is very
high, and the scenario notes carry the WHO extra-protection advice. Agent: daylight_seeker persona; preference passes through the tools;
sun and well-being tokens are added, and the verifier has sun and medical-claim rules. The scripted replay `daylight_seeker.json` matches
hero.json. Tests: 362 passed (new: test_sun_mode_agent 7, test_wellbeing +4). Known limit: monitor re-plans (delay/heat alert) are not
yet sun-aware.

## 2026-10-23 night - Stream D (Oslo, the second city)
Central Oslo baked with the unchanged city-agnostic pipeline (`zill.data.bake --city oslo`, then `zill.shade.bake --city oslo`).
Real counts (meta.json): 13,841 buildings in the caster ring (2,359 in scene, 1,050 parts; heights: 6,962 levels, 146 tag,
1,050 part, 5,683 fallback; max 117 m), 20,208 trees (19,777 mapped + 431 from rows), 7,247 nodes, 10,082 edges
(10,075 walk, 2,626 cycle; 128 covered, 540 indoor, 0 AC link), 53 POIs (13/13 curated landmarks resolved from OSM).
GLB 4.05 MB (62 tiles). Data bake 1,732 s wall (Overpass 502/504 retries); shade bake ~92 s for 4 dates
(winter 42 steps/28 day, spring 80/70, summer 119/107, hackathon 63/52). Logs: `data/raw/logs/oslo_bake.log`, `oslo_shade_bake.log`.
Low sun: per-city caster ring 1,500 m (117 m × 8.6 at 6.6°); night flag stored in exposure npz. Tests: `test_low_sun.py` (14),
`test_oslo.py` (7); full backend suite 369 passed (before the last lint-only edits), ruff clean.
Route Oslo S → City Hall works in both preferences (21 Jun 13:00: fastest 1,358 m / 605 s sun, coolest 1,536 m / 331 s,
sunniest 1,498 m / 1,063 s; 21 Dec 12:10: fastest 125 s sun, sunniest 2,321 m / 1,336 s).
Known: frontend `state/sun.ts` hard-codes Dubai ISO dates per preset id; Oslo needs the per-city `dates` from `/api/cities`.

## 2026-10-23 night - Stream A follow-up 2 (Oslo sun, sun-aware monitor)
Oslo weather was recorded: spring (2026-03-20) and summer (2026-06-21) from the archive, hackathon day from the forecast, and winter
(2026-12-21) as a labelled stand-in from the 2025-12-21 archive. Oslo sun search (S8):
- **solstice_midday_walk:** Akershus Fortress → Oslo Central Station (Oslo S) 13:00, from 5,944 jobs (2,543 eligible). Fastest is
  1,134 s with 73 s of direct sun. Sunniest is 1,391 s with 882 s of sun (+809 s) for +257 s. The sun is 6.3° high, your shadow is
  9.1× your height and UV is 0.1, so the daylight window is closed: this is about daylight and mood, not vitamin D.
- **summer_daylight_walk:** National Museum → Byporten Shopping 12:00, from 10,402 jobs (8,925 eligible). Fastest is 1,259 s with
  613 s of sun. Sunniest is 1,390 s with 1,288 s of sun (+675 s, +110 %) for +131 s. The window is open: sun 51.0°, UV 6.8 (high),
  1 % cloud, clear-sky index 1.0.
Monitor re-plans are now sun-aware. Tests: 373 passed (new: test_sun_mode_oslo 2, test_sun_mode_agent +2). Limits: leafless winter
trees are still modelled as blocking (TREE_BLOCK); cold stress is not modelled (heat band "none" at −3 °C).

## 2026-10-24 - Stream H (decks)
Rebuilt `docs/pitch/deck/index.html` to 17 slides (new: sun-mode proof, Oslo, well-being, accuracy, security, costs, users; expanded who-pays with B2G/schools/elderly care/events/real estate; freemium, no ads). `render.mjs` -> `Zill-and-Shams-pitch.pdf`; `deck/build_pptx.py` -> `Zill-and-Shams-pitch.pptx` (slide images + speaker notes, not editable text). Per-slide PNGs in `docs/pitch/qa/`. `GAMMA_PROMPT.md` updated. All numbers from hero.json, COSTS.md, SECURITY.md, ACCURACY.md, PROGRESS.md. [TEAM TO FILL] kept: Contabo price, per-1,000-user cost, VM CPUs. Stills in `deck/img/` are the old ones plus Oslo shade masks; swap files of the same name for new app stills.

## 2026-10-24 — Stream F (the app: Zill & Shams)
- Rename via brand constants (NAME "Zill & Shams", ظل وشمس, new tagline; OG/Twitter metadata). Shade ⇄ Sun toggle (shade #22333A / ember #D07A35), third route "Coolest"/"Sunniest", "sun saved"/"sun gained" from API fields; well-being card (UV band, feels-like, daylight / vitamin D window + "not medical advice", shadow ratio, breaks, overcast, weather Live/Recorded/Representative badge).
- Command bar: search-as-you-type (`/api/places/search`), one-line journeys (`/api/places/parse`) with an ambiguity picker, "online" label, ↑↓ Enter Esc, `?ask=` deep link. City switch from `/api/cities` (`/app?city=oslo`), bbox camera framing, city timezone and dates, honest night note, persona presets incl. Daylight seeker, sun hero journeys. 429 → "Busy, retrying in Ns". 375 px layout (bottom sheet).
- Gates: tsc, eslint clean; vitest 89/89 (12 files); `next build` green; backend test_smoke 4/4. QA: 5 iterations of stills (docs/qa/overnight-app/, git-ignored, ~110 MB), 8 best in docs/qa/best/app_overnight_*.jpg; /film smoke after /app?city=oslo: canvas back to Dubai, 0 console errors.
- Known: Oslo winter low sun renders the scene very warm/orange (lighting model at 7°); parser resolves "Oslo S" to Oslo Spektrum (Stream E); agent personas have no daylight seeker yet (backend).

## 2026-10-24 — Stream G (the film: Zill & Shams)
- 15 chapters, 790 s: title card Zill & Shams + ظل وشمس + new tagline; new "Two directions" (Burj Park → Boulevard Plaza, 15 Jan 12:30: shade mode 4.7 min in sun, fastest 5.2, sun mode 11.5; well-being card), "Winter in Oslo" (Akershus → Oslo S, 21 Dec 13:00, sun 6.3°, shadow 9.1×, fastest 1.2 vs sunniest 14.7 min sun, UV 0.1: "daylight and mood, not vitamin D"), "Safe and cheap to run" (privacy, controls, 16 security tests; costs/capacity from COSTS.md with the Contabo price left [TEAM TO FILL]); "Who pays" expanded (municipalities, schools/elderly care/events, well-being, cold cities; freemium, no ads); "Does it work?" adds accuracy + update frequency; "Any city." globe shows Oslo baked.
- Lighting: generic low-sun day grade (fixes the orange Oslo winter scene in /app and the film); Dubai unchanged.
- Gates: tsc + eslint clean, vitest 95/95, next build green, prod smoke /film + /app (0 CSP/console errors). QA: 2 full still iterations (45 each) + flicker probe in docs/qa/overnight-film/ (git-ignored, ~290 MB); best stills docs/qa/best/film_overnight_*.jpg.
- Known: SPEAKER_NOTES.md has no notes for the three new chapters (presenter strip falls back to titles); flicker probe shows window-speckle aliasing on dusk shots (~1–1.5% px, same as the ch01 baseline).
