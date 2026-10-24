# Handover: continue the Zill & Shams demo prep (2026-10-24)

Paste this whole file into a new Claude Code session opened in `D:\Projects\hackathons\zill` (or a cloud session on
github.com/mod-hamza/zill, branch `main`). The business pitch is today.

## Rules (binding)
- Commits as `mod-hamza <186332886+mod-hamza@users.noreply.github.com>` (repo-local config), **no Co-Authored-By lines**.
- Pushing to `main` auto-deploys to https://zill.itshamza.me within ~5 min (VM timer runs `deploy/cd.sh`).
- Never fabricate numbers; never show `[TEAM TO FILL]` anywhere (the user wants zero placeholders: source it or drop it).
- Don't commit `README.md` (user's own edits). `.env` is git-ignored; never commit keys.
- VM: `root@169.58.66.146`, use Windows ssh-agent `C:\Windows\System32\OpenSSH\ssh.exe` (Git Bash ssh can't see the
  agent). Shared VM (n8n, searxng, nocturne-jam): never restart other containers.

## State
- Live: renamed Zill & Shams app (Shade/Sun toggle, well-being card, typed places "from X to Y", Dubai + Oslo),
  security hardening, costs ($6.93 VPS, ~$17/month fixed), 15-chapter film, 17-slide decks (docs/pitch/).
- Case studies with real engine numbers: `data/scenarios/case_studies.json` (hotel guest, rider, Oslo winter,
  Dubai dawn run, Oslo lunch run). Run mode (2.8 m/s) exists.
- LLM client (`backend/zill/agent/llm.py`) walks models on 429 and waits out throttling (bounded).

## In progress / remaining (in order)
1. **Film 6-minute cut** — a sub-agent was building it: the short cut must be served at **/film** and the old full
   film at **/film2** (unlinked). Check `git status`: uncommitted work in `frontend/src/film/**`,
   `frontend/src/app/(stage)/film/page.tsx`, `frontend/src/app/(stage)/film2/`, `frontend/next.config.ts`,
   `frontend/e2e/film.spec.ts`, `frontend/scripts/*`, `frontend/public/film-data/*`. Short-cut order (~360 s): Title,
   Shade moves, City built, Two directions, **Case studies** (hotel→guests, employers like Talabat/Noon→riders as
   *example target customers only*, Oslo winter daylight, running clubs), Who pays (with concrete pricing hypotheses:
   hotels ~$99/property/mo, fleets ~$1/rider/mo, employers ~$49/site/mo, city licence ~$15k/yr, corporate well-being
   ~$12/employee/yr, consumer premium ~$2.99/mo; no market-size placeholders), Safe and cheap to run, Try it.
   Finish it, then `cd frontend && npm run typecheck && npm run lint && npx vitest run && npm run build`.
   Then `grep -rn "TEAM TO FILL\|TO VALIDATE" frontend/src` must return nothing rendered. Visually check stills.
2. **Live LLM = Gemini** (free tier, OpenAI-compatible). Local `.env` already has it (see `.env`). Put the same lines
   into `/home/hamza/zill/.env` on the VM, then `/home/hamza/zill/deploy/cd.sh --force`:
   ```
   ZILL_LLM_PROVIDERS=voke
   ZILL_VOKE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
   ZILL_VOKE_API_KEY=<Gemini key from local .env>
   ZILL_VOKE_MODEL=gemini-2.5-flash
   ZILL_VOKE_MODEL_FAST=gemini-2.5-flash-lite
   ZILL_VOKE_FALLBACK_MODELS=gemini-flash-latest,gemini-2.5-flash-lite,gemini-flash-lite-latest
   ```
   Check https://zill.itshamza.me/api/health shows the provider, then try the agent in /app. Optionally re-record
   replays live: `backend/.venv/Scripts/python.exe scripts/record_replay.py --live` (writes `backend/replay/`; then
   `cd frontend && node scripts/sync-film-data.mjs`), but only commit them if every session completes without an
   `error` event; otherwise keep the existing recordings.
3. Full tests: `uv run scripts/zill.py test` (backend ~383, frontend ~95), commit, push, verify live /film, /film2,
   /app (Dubai + Oslo), agent panel.
4. Deck stills: decks are in docs/pitch (rebuild: from `frontend/`: `node ../docs/pitch/deck/render.mjs ../docs/pitch/qa`,
   then `node ../docs/pitch/deck/extract.mjs` and `python ../docs/pitch/deck/build_pptx.py`).
