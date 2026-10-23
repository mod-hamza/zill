# VALIDATION

What we measured, what the tests prove, and where the model is weak. Every number cites the file it came from. Test totals were refreshed with `python scripts/zill.py test` on 2026-10-23 01:51 (`data/test_results.json`).

## 1. Test results

| Suite | Result | Source |
| --- | --- | --- |
| Backend pytest | 221 passed, 0 failed | `data/test_results.json` |
| Frontend vitest | 69 passed, 0 failed (8 files) | `data/test_results.json` |
| Frontend typecheck, ESLint | clean at the time of the run | `python scripts/zill.py test` |

Backend tests per file (from `pytest --collect-only`): tokens 34, agent orchestrator/monitor 26, routing 15, shade ray-march 14, replay 14, heights 13, LLM client 13, agent tools 12, API routes 12, sun 10, API cities 7, synthetic bake 7, planner 7, weather 7, departure 5, geo 4, Dubai data 4, shade pipeline 4, real-engine agent 4, smoke 4, scenarios 3, SSE 2.

Run everything with `make test` (or `python scripts/zill.py test`). Re-run it after any change and before the pitch; it rewrites `data/test_results.json`, which Film chapter 5 reads.

## 2. Data quality (Phase 1 bake)

Source: OpenStreetMap via Overpass (`overpass-api.de`), OSM base timestamp 2026-10-22T19:17Z. (c) OpenStreetMap contributors (ODbL). Re-bake from cache: `python -m zill.data.bake --city dubai_downtown` (about 8 s); `--refresh` refetches. All counts below are from `data/cities/dubai_downtown/meta.json`.

| Item | Value |
| --- | --- |
| Buildings in caster box (core + 900 m) | 8,602 (3,039 in the rendered scene = core + 100 m) |
| `building:part` polygons | 577; 97 shells replaced by parts, 132 shells kept minus partial parts |
| Height source | tag 1,098 / levels 167 / **fallback 6,760** / part 576 / landmark 1 |
| Max height | 828 m (Burj Khalifa spire part; OSM tags 760 m, curated override) |
| Trees | 744 (547 mapped nodes + 197 sampled every 6 m along 11 tree rows); none carry crown or height tags, so defaults r 3 m, h 7 m |
| Graph | 5,455 nodes, 7,659 edges (7,031 walk, 4,822 cycle/scooter), median edge 21 m, 302 km; incl. 2 `entrance_link` edges (OSM doors whose outside path is unmapped) |
| Link classes (counts) | open 6,080 / indoor 1,446 / covered 116 / ac_link 15 |
| Dropped components | walk 40, cycle 23 (95 edges) |
| POIs | 50 (18 of 19 curated gazetteer entries resolved; Vida Downtown dropped) |
| `buildings.glb` | 152 tiles of 250 m, 112,115 vertices, 61,407 triangles, 4.5 MB (`glb_report.json`) |

Burj Khalifa top at 828 m is asserted in `backend/tests/test_data_heights.py` and `test_data_dubai.py`.

Honest caveats:

- **Heights are mostly guessed.** 6,760 of 8,602 footprints (about 79 %) have no height or levels tag and use the PRD fallbacks (apartments 30 m, hotel 45 m, office 40 m, retail 22 m, default 18 m). Shadow lengths of those buildings are approximate. Overture heights are a P2 option.
- **Trees are under-estimated.** OSM tree mapping in Downtown Dubai is sparse, so tree shade is conservative.
- **Graph density.** The PRD gate expected more than 10,000 edges; the real network for the scene box gives 7,659 after splitting at every shared node. Accepted, not padded (`docs/DECISIONS.md`). Many roads carry `foot=no` because sidewalks are mapped separately; they are cycle-only.
- **AC links come from OSM tags** (`bridge=yes` with `covered=yes` or `indoor=yes`), including the Metro Link (way/204267696), continuous from the station into the Dubai Mall indoor network. Not yet walked on site.
- **Entrances.** 27 indoor/outdoor transitions are accepted as doors because they lie within 3 m of a building wall; 1 curated entrance (node 605023848) reconnects about 1,500 edges west of Sheikh Zayed Road (`meta.json` diagnostics).

POI snaps (distance to nearest walk node): burj_khalifa 33 m, dubai_mall 6 m, dubai_fountain 78 m (in the lake), dubai_opera 38 m, metro_burj_khalifa 14 m, souk_al_bahar 49 m, burj_park 43 m, address_downtown 38 m, armani_hotel 16 m, palace_downtown 48 m, boulevard_plaza 0 m, emaar_square 8 m, address_boulevard 42 m, address_sky_view 14 m, burj_lake 88 m, business_bay_metro 44 m. Full list in `data/cities/dubai_downtown/pois.json`. QA images: `docs/qa/phase1/`.

## 3. Shade engine

Bake summary (`data/cities/dubai_downtown/shade/bake_log.json`): caster grid 2,283 x 2,412 and core grid 1,483 x 1,612 at 2 m; winter 71 steps (06:40-18:20), spring 83 (05:30-19:10), summer 88 (05:10-19:40), hackathon 74 (06:00-18:10); 28.9 MB of PNGs, 1.0 MB of exposure arrays.

Geometry tests (`backend/tests/test_shade_raymarch.py`, `test_shade_pipeline.py`, `test_sun.py`):

- lone box at 45 degrees altitude gives the right shadow length and direction for several azimuths
- shadow length scales with altitude; zenith sun shades only the footprint; night is all dark
- gap between two boxes is shaded only when geometry says so
- 90-degree rotation symmetry (rotating scene and azimuth gives the rotated raster)
- tree canopy gives partial shade, including directly beneath at noon
- heightmap orientation, polygon holes, floating parts that block rays but are not footprints
- sun position vs pvlib goldens (`data/curated/sun_golden.json`, 20 samples) within 0.5 degrees, in both Python and the frontend (`frontend/src/lib/sun.test.ts`); solstice noon altitudes and sunrise/sunset checks

Visual alignment (PRD 18.3 step 4), checked in `docs/qa/phase2/` and `docs/qa/phase6/`: at 12:00 on the hackathon date shadows fall north, at 16:00 they fall east-north-east, raster edges start at building bases, and the real-time shadow map agrees with the raster.

## 4. Routing invariants

`backend/tests/test_routing.py` (15 tests) and `test_departure.py`: arrival-time lookup (not departure-time), time-dependent route choice changes, A* matches Dijkstra cost, covered edges are sun-free, cycle never uses stairs or foot-only ways, Coolest never has more sun exposure than Fastest, origin equals destination, and a random-pair invariant sweep on both the synthetic city and the real Dubai data (`test_invariants_real_data`, passes with no skips). Departure: table shape and timing, monotonic in the waiting weight, latest-arrival constraint, "already best" case.

## 5. Agent validation

- Token resolver and numeric guard: 34 tests including a 240-case fuzz of adversarial outputs with bare numbers (`backend/tests/test_tokens.py`). Any digit or spelled-out cardinal not from a token or the user's own message is rejected or rewritten.
- Tools: 12 tests; orchestrator, verifier, monitor, autonomy levels, undo: 26 tests; real-engine agent run on the synthetic city: 4.
- Replay: 14 tests (ordering, phases, badge, free-text fallback). The four shipped recordings (`backend/replay/`) are **scripted, not live** (`live: false`, model `zill-scripted-planner`). They issue real tool calls against the real engine and are validated against `hero.json`, but no LLM was involved. They are badged "Scripted session (live model not connected)" in the UI.
- Verifier: the LLM verification layer only runs with a live model; scripted sessions report `layers: ["deterministic"]`.

## 6. Hero results (the money shots)

From `data/scenarios/hero.json` (generated 2026-10-23T01:17:57+04:00, `search.attempts`). Re-check these if the file is regenerated.

| Scenario | Fastest | Coolest | Sun saved | Added time | RHL saved |
| --- | --- | --- | --- | --- | --- |
| Tourist walk, Dubai Opera to Business Bay Metro, summer 15:30 | 24.3 min, 15.2 min in sun, 37 % shaded | 26.4 min, 9.0 min in sun, 66 % shaded | 371.8 s (6.2 min, 40.8 %) | +131.8 s (2.2 min) | 17.8 % |
| Rider cycle, Maryland International Hotel to Taj Dubai Hotel, 15:30 | 9.0 min, 7.4 min in sun | 10.6 min, 4.6 min in sun | 170.7 s (38.2 %) | +93.6 s | 16.3 % |
| Crew walk, Address Boulevard to Address Sky View, 14:30 | 10.0 min, 6.4 min in sun | 10.7 min, 3.8 min in sun | 155.3 s (40.3 %) | +43.7 s | 18.6 % |

Honest findings:

- The tourist saving (372 s) is above the PRD's 90 s widening threshold; no search widening was needed.
- **The departure optimiser found no better time for the tourist trip.** Over 15:30-17:00 the recommended departure is 15:30 itself (`departure.recommended`, empty `why.changes`). The Balanced route's sun exposure falls from 569 s at 15:30 to 515 s at 16:30, a gain of 54 s that costs a 60-minute wait, so the waiting cost wins. Chapter 7 must present this honestly: "leaving later does not help this trip" is the real result.
- The AC-link story (`hero.json["ac_link_story"]`): Burj Khalifa/Dubai Mall Metro to The Dubai Mall at 13:30 in summer is 1,438 m, 19.7 min, 0 s in sun, 100 % indoor. With the link removed the mall is unreachable in the graph, so there is no outdoor comparison. The link is unverified on site.
- The crew shuttle's Balanced and Coolest routes are identical (`hero.json`).
- RHL and the UV factor are model heuristics. They are not measurements.

## 7. Limits (say these out loud)

1. Shade is from buildings, mapped trees and covered links only. Awnings, unmapped trees, vehicles and wind are not modelled. Label in the UI: "Model v1: buildings, mapped trees, covered links".
2. 79 % of building heights are fallbacks, so some shadows are too long or too short.
3. The graph has 7,657 edges; footpaths missing from OSM do not exist for the router.
4. The AC link and the metro entrance connection are unverified on site.
5. Exposure is time-of-day only for a given preset date; other dates need on-demand computation (`POST /api/shade/compute`), and un-baked dates return HTTP 409 until computed.
6. Weather does not change shadows. Weather files are real Open-Meteo data (`data/weather_cache/*.json`: archive for winter, spring, summer; forecast for hackathon fetched 2026-10-22); UV for archive dates is a labelled clear-sky estimate.
7. The UAE midday-break pack is unverified (`data/curated/policy_packs/uae_outdoor_work.json`, `verified: false`). Not legal advice.
8. Scripted agent sessions, not live; the live model path is implemented and tested with a fake LLM but has not run against the real endpoint because no key was present.
9. The e-scooter mode is cycle rules with a higher speed; UAE lane rules are simplified.
10. There is no field measurement yet (section 9).

## 8. Performance

Measured 2026-10-23 on the dev laptop (24 logical cores, RTX 4070 Laptop GPU) while other build jobs ran, so numbers are noisy upper-ish bounds. Earlier runs the same night were between these and 2x worse under heavier load (first pass: single route p95 56.6 ms, triple p95 213.4 ms, departure 93.4 ms). The routing stream also reported a quiet-machine run of single p95 16.8 ms, triple p95 46.7 ms, departure 19x 34 ms in its hand-off; that run is not stored in the repo, so the committed repro is below.

| Metric | Result | Gate (PRD) | Source / command |
| --- | --- | --- | --- |
| Shade step (kernel) | mean 0.53-0.62 s, max 0.82 s on the real grid | 2.5 s | `shade/bake_log.json`; PROGRESS: mean 0.72 s, max 1.08 s |
| Shade step with PNG write, concurrent load | 1.55-1.90 s | 2.5 s | `docs/PROGRESS.md` |
| Route, lambda 3 (100 pairs) | p50 7.6, p95 25.1, max 39.2 ms | 300 ms | `docs/qa/phase9/bench_routing.json` |
| Route with segments and baseline | p50 11.9, p95 43.0 ms | 300 ms | same |
| Route triple | p50 21.2, p95 68.8, max 101.2 ms | 300 ms | same |
| Departure, 19 rows | 38.3 ms | 3 s | same |
| Scene frame time (high / medium / low) | p95 12.2 / 11.2 / 10.1 ms; 114 / 125 / 140 fps; 135-162 draw calls | 60 fps | `docs/qa/phase6/perf.json` (App, vsync off, ANGLE D3D11) |
| Film chapters 4-6 p95 frame time | [TEAM TO FILL, measure with `/film?debug` after the film is final] | 60 fps | see OPEN_ITEMS |

Reproduce: `cd backend && .venv/Scripts/python.exe -m zill.routing.bench --n 100`.

## 9. Field-test plan (not yet done)

Goal: check that modelled shade matches the street. On the Boulevard around 14:00, with an IR thermometer, take paired readings of a shaded and a sunlit surface (and air temperature if possible) at 6 or more places the model marks shaded vs sunny, plus one walk of the Metro to Dubai Mall link. Record to `data/validation/field_test.json` with schema `[{ts, place, shaded: bool, surface_c, air_c?, note}]`. Film chapter 10 shows the table when the file exists and a "result pending" card otherwise. Until then, accuracy claims are limited to the geometry tests above. The file does not exist yet.

## 10. QA artefacts

`docs/qa/phase1/` (graph, buildings), `docs/qa/phase2/` (shadow previews at 08:00, 12:00, 13:30, 16:00), `docs/qa/phase6/` (App iterations and `perf.json`), `docs/qa/phase9/bench_routing.json`.

Routing sanity (graph-level + `zill.routing.tdsp.route`, walk, summer 13:30): Burj Khalifa → The Dubai Mall 447 m / 6.1 min, 100 % indoor via the OSM-mapped tower–mall link (the same route without any ac_link edge); Souk Al Bahar → Dubai Mall 385 m; Dubai Opera → Dubai Mall 1,140 m (fastest) / 1,178 m (coolest, 425 → 356 s in sun); Metro station → Dubai Mall 1,439 m via the Metro Link (ac_link 838 m). The mall connects to outdoor paths through 7 OSM `entrance=*` doors plus 2 short entrance links — not only through the Metro Link.
