# Common rules for every Zill sub-agent (read first)

1. Read `CLAUDE.md`, `docs/CONTRACTS.md` (binding formats + file ownership), and the PRD sections your brief lists. Read them fully.
2. Work autonomously. Never ask questions. When ambiguous: choose the PRD default or the most conservative option, append ONE line to `docs/DECISIONS.md` (`- <date> <stream>: what — why`).
3. Edit ONLY files your brief says you own. If you need a change in another stream's file, do not make it — describe it in your final report under "Requests for other streams".
4. **Never run** `git commit`, `git add`, `git reset`, `git checkout`, `git stash`, `git clean`. The orchestrator commits. Read-only git is fine.
5. Python: use `backend/.venv/Scripts/python.exe` (Windows). Install extra deps with `uv pip install --python backend/.venv <pkg>` AND add them to `backend/pyproject.toml` dependencies (that one-line append is allowed for all streams). Run tests from `backend/`: `.venv/Scripts/python.exe -m pytest -q tests/<yourfiles>`.
6. Frontend: npm in `frontend/`. Adding deps is allowed (`npm i <pkg>`); note them in your report.
7. Truthfulness (CLAUDE.md): never fabricate data, results or numbers. Placeholders as `[TEAM TO FILL — cite source]` + a line in `docs/OPEN_ITEMS.md`. Simulated/cached things labelled as such.
8. Tests first for engine code. Your work is "done" only when your gate tests pass and ruff (`.venv/Scripts/python.exe -m ruff check zill tests`) / `npm run typecheck && npm run lint` are clean for your files.
9. Network: allowed for installs and Overpass/Open-Meteo. Overpass requires a User-Agent header — use `Zill-hackathon-prototype/0.1` (do NOT put any email address in requests). Only `https://overpass-api.de/api/interpreter` was reliable at 22:45; others timed out.
10. Do not spend > 25 min on a single blocker: take the PRD fallback, log it.
11. Append a short entry to `docs/PROGRESS.md` when done (timestamp, stream, what exists, test counts, known issues).
12. Final report to the orchestrator (≤ 300 words): files created, gate results with real numbers, deviations, requests for other streams, known issues.
13. Long-running commands (bakes, builds) → run them with a timeout and keep logs in `data/raw/logs/` or your scratch dir; don't flood your context with raw output (use `tail`).
