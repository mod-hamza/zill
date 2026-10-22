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
