# PROGRESS.md — running log

## 2026-10-22 22:40 · Phase 0 starting
- Read PRD.md + CLAUDE.md. Git repo initialised locally (no remote yet). GNU make installed.
- Wrote `docs/CONTRACTS.md` (shared data/API formats + file ownership) and `docs/DECISIONS.md`.
- LLM: OpenAI-compatible Voke endpoint; API key not yet present → agent will be built with replay/scripted fallback until `.env` has a key.
- Next: Phase 0 scaffold (sub-agent), then parallel streams: data bake, shade engine, routing, agent, 3D scene.

## 2026-10-22 22:45 · Phase 0 scaffold
- Backend skeleton (config, brand, geo, /api/health, /api/config), Next 15 frontend (routes /film /app /health /embed/hotel, tokens, fonts), scripts/zill.py, Makefile, docs stubs.
- Gate: make setup OK; pytest 4 passed; vitest 3 passed; typecheck/lint/build clean; demo served /film and proxied /api/health; Playwright smoke 1 passed; ports freed.
