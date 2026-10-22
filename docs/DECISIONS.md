# DECISIONS.md — one line per decision (what, why)

- 2026-10-22 LLM provider = OpenAI-compatible "Voke" endpoint (https://www.vokeapi.com/v1) via `openai` SDK, not the Anthropic SDK — user instruction; key supplied later in `.env`.
- 2026-10-22 Python 3.11 via `uv` venv at `backend/.venv` — system default is 3.10, `py` is 3.14 (numba support lags); PRD requires 3.11+.
- 2026-10-22 GnuWin32 make installed via winget; Makefile recipes delegate to `python scripts/zill.py <target>` so behaviour is identical on Windows/Mac/Linux and runnable without make.
- 2026-10-22 npm (not pnpm) for the frontend — default tooling, fewer surprises in the clean-clone test.
- 2026-10-22 Shared interfaces pinned in `docs/CONTRACTS.md` before parallel work begins (grid orientation: row 0 = north, col 0 = west).
- 2026-10-22 Work is split across sub-agents by directory ownership; only the orchestrator commits.
- 2026-10-22 @types/node bumped to ^24 (vitest 5 peer requires >=22); create-next-app default ^20 caused ERESOLVE.
- 2026-10-22 Added backend/zill/geo.py in Phase 0 (CONTRACTS lists it as scaffold-owned) with round-trip test; frontend/src/lib/geo.ts mirrors it.
- 2026-10-22 Removed create-next-app boilerplate (README, svgs, favicon); frontend/.gitignore kept (ignores next-env.d.ts, .env*).
