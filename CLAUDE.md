# CLAUDE.md — standing rules for the Zill build (read first, every session)

You are building **Zill** from `PRD.md`. This file is your operating manual. `PRD.md` is the spec. If they conflict, `PRD.md` wins on product, this file wins on process.

## Operating mode: unattended overnight
- **Never stop to ask questions.** No humans are available. Choose the PRD default, or the most conservative sensible option, write one line in `docs/DECISIONS.md` (what, why), and continue.
- **Never end a turn idle while work remains.** After each phase, immediately start the next. Only stop when Phase 10 gates are all green (or Phase 11 if time allows).
- Keep `docs/PROGRESS.md` as a running log: timestamp, phase, what was done, what's next, known issues. Update it at every commit.
- **Commit at every green gate** (`git commit`, tag `phase-N-green`). Small, meaningful commits. Never leave the repo in a broken state; if an experiment fails, revert it.
- If a dependency or API fails, **diagnose, work around, log it**. Network is available for installs and Overpass; if Overpass is slow, use mirrors, cache, retry with backoff. Don't burn more than ~25 minutes on any single blocker before taking the PRD's fallback.
- Protect the **cut-line** (PRD §4): finish P0 completely and polished before P1; P1 before P2. Do not start P2 until all gates through Phase 10 are green.

## Truthfulness rules (these protect the team in front of judges)
- Never fabricate data, test results, field measurements, statistics, or market numbers. Use `[TEAM TO FILL — cite source]` placeholders and list them in `docs/OPEN_ITEMS.md`.
- Anything simulated or cached is **labelled as such in the UI** (`Simulated`, `Recorded session`, `Cached build`, `Representative profile`).
- If a result is modest (e.g. a small sun saving on the hero route), report it honestly. Never tune parameters just to inflate the headline figure. Choose scenarios by the documented search procedure.
- Numbers in agent output must come from tool results via `{{tokens}}` (PRD §11.4).

## Engineering standards
- Python 3.11+, type hints, Pydantic v2, `ruff` + `pytest`. TypeScript **strict**, ESLint clean. No `any` without a comment.
- Deterministic cinematics: every Film chapter is a pure function of chapter-local `t`. No timers in animation logic.
- One source of truth for constants (`config.py`, mirrored to the frontend). No magic numbers in components.
- No runtime CDN or network dependence for the Film/App (fonts, models, textures self-hosted).
- Secrets only in `.env` (git-ignored); never log the API key.
- Performance matters: instancing/merged geometry, texture size discipline, quality tiers.
- Tests first for the engine (shadow geometry, routing invariants). A green test suite is part of the pitch.

## Design standards (PRD §12, strictly)
Premium, warm, cinematic, restrained. Serif display + clean sans. Palette from `design/tokens.ts`. **Banned:** neon, cyan/magenta/electric-blue, purple-blue gradients, glassmorphism, glowing grids, sparkles, emoji, circuit/hex textures, terminal-green, heavy drop shadows, lens flares.

## Seeing your work (mandatory visual QA loop, PRD §18.3)
You can read images. After every frontend phase, capture Playwright stills of all chapters/states, **open them and critique them**, fix, re-capture, repeat at least twice. Specifically check: shade overlay aligned with buildings, shadows point away from the sun disc, text legible, nothing clipped/overlapping, the route clearly readable, palette on-brand. Save to `docs/qa/<phase>/`.

## Task management
- Use sub-agents/parallel work where it speeds things up and files don't collide (e.g. backend engine vs frontend scaffolding in Phases 2–3 / 6), but integrate and test on the main branch before tagging a gate.
- Prefer finishing a smaller scope beautifully over a larger scope poorly.

## Before you finish (the last 60–90 minutes of your work)
1. `make test` green. 2. Fresh-clone test: clone the repo to a temp dir, `make setup && make demo`, load `/film` and `/app`, run Playwright smoke. 3. Write/refresh all `docs/*`. 4. Produce deck stills + backup videos (`make record`). 5. Final `docs/PROGRESS.md` summary: what exists, what's cut, the exact start command, the top 5 risks for the presenters, and what the humans must do (OPEN_ITEMS).
