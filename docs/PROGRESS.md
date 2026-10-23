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
