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
