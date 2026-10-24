# OPEN_ITEMS.md — things the humans must resolve

Grouped checklist. Tick items as you finish them. Every placeholder and unverified item from every stream is here.

## Before the pitch

- [ ] Add `ZILL_LLM_API_KEY` (Voke) to `.env` and confirm model ids (`ZILL_MODEL`, `ZILL_MODEL_FAST`); `/health` model row should go green.
- [ ] Once the key is in `.env`, run `backend/.venv/Scripts/python scripts/record_replay.py --live` to re-record all four sessions with the real model (`live: true`), then `cd backend && .venv/Scripts/python -m pytest -q tests/test_replay.py`. Until then the four recordings in `backend/replay/` are **scripted, not live** (`live: false`, model `zill-scripted-planner`) and are badged "Scripted session (live model not connected)". Do not call them live or "recorded model output" on stage.
- [ ] Re-record hackathon-day weather: `cd backend && .venv/Scripts/python -m zill.weather.record` on 2026-10-23 or 24 (the hackathon file is a forecast fetched 2026-10-22).
- [ ] After the film is final: `python scripts/zill.py record` (backup film and app videos, 14 deck stills) and open every still and both videos; confirm the stills carry the right moment of each chapter (`frontend/scripts/export-deck-assets.ts`, `PLAN` table).
- [ ] After the film is final: run `python scripts/zill.py freshclone` on committed code with ports 3000/8000 free; must print PASS.
- [ ] Re-run `python scripts/zill.py test` so `data/test_results.json` (Film chapter 5) matches the final code, and refresh the test totals in `docs/VALIDATION.md` section 1.
- [x] Film chapters 4-6 p95 frame time: `docs/VALIDATION.md` now says "not yet measured"; measure with `/film?debug` if time allows.
- [ ] If `data/scenarios/hero.json` is regenerated, re-check every figure in `docs/SPEAKER_NOTES.md` and `docs/VALIDATION.md` section 6.
- [ ] Rehearse once with `/film?presenter=1` and time it; speed range 0.85x-1.15x gives about 11:20-15:20.

## Verify on site

- [ ] Verify the UAE midday-break rule dates and hours and any current e-scooter lane rules before presenting. Policy pack: `data/curated/policy_packs/uae_outdoor_work.json` (`verified: false`, window 12:30-15:00, 15 Jun-15 Sep, max continuous sun 45 min, min break 10 min). Shown in the UI as "Policy pack: UAE midday break (v1, verify)". Not legal advice.
- [ ] Verify curated/derived AC links on site: walk the Metro to Dubai Mall link and confirm it is enclosed and air-conditioned end to end. OSM ways 204267696, 47517411, 700932968, 700932969, 237251660, 1092739433 are classed `ac_link` from `covered=yes`/`indoor=yes` tags (15 edges).
- [ ] Confirm the public pedestrian connection at curated entrance node 605023848 (metro station area), auto-added so the area west of Sheikh Zayed Rd stays reachable on foot.
- [ ] Spot-check mall doors: 27 indoor/outdoor transition nodes were accepted as doors because they lie within 3 m of a building wall (no `entrance=*` tag).
- [ ] Collect field-test readings with an IR thermometer for Chapter 10 into `data/validation/field_test.json` (schema `[{ts, place, shaded: bool, surface_c, air_c?, note}]`; plan in `docs/VALIDATION.md` section 9). Without it chapter 10 shows "result pending".
- [ ] Confirm slot length (15 vs 20 minutes) with organisers; confirm projector resolution and aspect ratio; test the laptop on the projector.

## Fill in (placeholders in the pitch)

- [x] Heat and market statistics: sourced in `docs/SPEAKER_NOTES.md` (Dubai Airport NOAA 1991-2020 normals: 41.5/41.9 C mean daily max Jul/Aug; 154,000+ hotel rooms, 827 establishments, DET via Khaleej Times; 70,000+ riders, RTA). No sourced outdoor-employer size, so none is stated. Film Ch.1/2/9 still hard-code placeholders in `src/film/**` (see report).
- [ ] Validate the pricing hypotheses with mentors (Dr Maria Haynes, 3:00 PM managerial session). They are now stated as hypotheses: hotels ~$99/property/month; fleets ~$1/rider/month; outdoor employers ~$49/site/month; city/tourism licence ~$15,000/year; consumer premium ~$2.99/month, no ads.
- [x] Competitors: rephrased to "mainstream routing apps optimise time and distance", no unverified claims (`docs/SPEAKER_NOTES.md`).
- [ ] Hotel/fleet interview evidence and the specific ask on the last slide: placeholders in `docs/SPEAKER_NOTES.md`.
- [ ] Burj Khalifa height override 828 m (`data/curated/dubai_downtown/landmarks.json`, spire part way/137153144; OSM says 760 m) is `verified: false`; cite CTBUH if shown on screen.
- [x] Weather fallback: monthly low/high now Dubai Airport 1991-2020 NOAA normals (https://en.wikipedia.org/wiki/Climate_of_Dubai); humidity and wind stay approximate and labelled as such, `synthetic_representative`.
- [ ] UV for archive dates is a clear-sky estimate (`uv_basis: clear_sky_estimate`), labelled as such; mention if asked.

## Decisions

- [ ] Confirm tagline and name (name lives in `frontend/src/brand.ts` / `backend/zill/brand.py`; one-line rename).
- [ ] Graph has 7,659 edges against the PRD gate of 10,000 (real OSM density, see `docs/VALIDATION.md` section 2): accept, or change the gate.
- [ ] 79 % of buildings use fallback heights (no height/levels tag): accept with the stated caveat, or add Overture heights (P2).
- [ ] OSM trees are sparse (744 in the caster box, none with crown/height tags), so tree shade is under-estimated: accept (conservative), or add a tree layer.
- [ ] Router constants are heuristics, not measurements: `uv(alt) = clip(sin^0.6)`, RHL weights 1.0/0.35/0.1, crowd x1.15 indoors, crossing waits, planner break threshold `RHL_BREAK_THRESHOLD = 1200` (`backend/zill/config.py`). Validate with the field test.
- [ ] Extra cities and the Chapter 4 morph (P2) were not built unless noted in `docs/PROGRESS.md`; chapter 11 shows only Downtown Dubai as baked.
- [x] In-browser stills fallback for WebGL failure (PRD 17.4): `/film` shows `public/stills/manifest.json` stills with ←/→ when WebGL is unavailable or the context is lost (`src/film/StillsFallback.tsx`).
- [ ] Scripted (not live) agent sessions are badged as such in the UI; decide whether to re-record live (see above) or present them as scripted.
- [ ] The fleet view and the crew view are scenario simulations and labelled "Simulated"; confirm you are comfortable presenting them that way.
- [ ] Film Ch.9: sourced market context available (154,000+ hotel rooms / 827 establishments; 70,000+ riders; 19.59 M visitors 2025); outdoor-employer size has no source; rider "trips per shift" dropped. The film file still renders placeholders until edited.
- [ ] Film Ch.10: field-test card says "result pending" until `data/validation/field_test.json` exists (then re-run `npm run sync:film`).
- [ ] Film Ch.9 crew vignette shows the UAE midday-break window from the UNVERIFIED policy pack (`data/curated/policy_packs/uae_outdoor_work.json`), labelled "verify".
- [ ] Film data copies: after re-recording replays, re-running `make test`, or editing SPEAKER_NOTES, run `npm run sync:film` (also runs automatically on `npm run dev` / `npm run build`).
- [ ] Film Ch.11 roadmap cities (Doha, Riyadh, Singapore, Phoenix) are a team choice from the PRD; confirm.
- [ ] [data] 2 auto-generated `entrance_link` edges (≤ 30 m, from OSM doors 8423933513 and 8423933514 to the nearest outdoor path) are `verified:false` — confirm the doors open onto those paths
- [ ] [data] Burj Khalifa POI now snaps to the tower's OSM entrance, whose only mapped path is the indoor link into The Dubai Mall — confirm the public visitor route (At the Top visitors enter through the mall)

## Overnight pivot (2026-10-24): what the humans must do
- [ ] **LLM key (most important for judging):** add `ZILL_OPENCODE_API_KEY=...` (and/or `ZILL_VOKE_API_KEY`) to `/home/hamza/zill/.env` on the VM, then run `/home/hamza/zill/deploy/cd.sh --force`. Until then the agent plays labelled recordings. See `docs/LLM.md`. Then re-record the replays live (`python scripts/record_replay.py`).
- [x] Contabo plan price $6.93/month in `docs/COSTS.md`, deck and facts.json. Per-token prices not used (flat subscription).
- [ ] **OpenCode Go monthly caps**: confirm the per-model limits in `docs/LLM.md` against opencode.ai/docs/go (the scrape merged the Go and Go Plus columns).
- [ ] **Oslo winter weather** is a labelled stand-in (2025-12-21 archive), because 2026-12-21 is beyond the forecast range.
- [ ] **npm audit**: 2 findings in PostCSS bundled with `next`; the fix is next@16 (breaking), not applied.
- [ ] **Weekly map re-bake** is the stated production plan, not yet scheduled (`docs/ACCURACY.md`).
- [ ] Optional: apply the header lines in `deploy/Caddyfile.snippet` to the VM's Caddyfile (the API already sends its own security headers).
