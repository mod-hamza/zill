# ZILL — Product Requirements Document (v1.0)

> Working name: **Zill** (ظل, "shade"). The team may rename it; keep the name in ONE config file (`brand.ts` / `brand.py`) so renaming is a one-line change.
> Team: Abhamzay (Team 13). Event: AI Agents Hackathon, American University in Dubai. Pitch: **12–14 minutes**, judges only, in a room.
> Reader: Claude Code (Opus), running **unattended overnight**. Everything you need is in this file. Do not ask questions. Where something is ambiguous, pick the stated default, log it in `docs/DECISIONS.md`, and keep moving.

---

## 0. TL;DR

Build **Zill**: an AI agent that plans walking, cycling and scooter journeys through the **shade**, for hot cities. It builds a 3D model of a city from open data (OpenStreetMap), computes where the sun's shadows fall at any minute of any day, and routes people through shade and air-conditioned links. The agent also plans whole days, picks the best departure time, and replans proactively when things change.

You are building **three things**, all in one monorepo:

1. **The Engine + Agent (Python/FastAPI).** Real data, real sun maths, real shadow casting, real time-dependent routing, a real tool-using Claude agent. **This must genuinely work.** Judges score 50% on technical feasibility.
2. **The Film (`/film`).** A long, cinematic, scroll-driven 3D landing page that *is* the pitch visuals. The presenter talks over it for 12–14 minutes. It shows the city being built, the shade engine, a route being planned with the camera flying through the city, the agent reasoning, and the business case. Every number on it comes from the real engine output (or is explicitly marked as a placeholder for the team to fill).
3. **The App (`/app`).** The live, interactive product, used for the "try it" moment and Q&A.

**Hero city: Downtown Dubai.** It must be flawless. A second city is a stretch goal (see §4).

**Quality bar:** premium, cinematic, warm, restrained. Think architectural film, not sci-fi dashboard. See §12. **Zero neon. Zero "AI glow".**

---

## 1. Context you must internalise

### 1.1 How this is judged
- **50% Technical feasibility.** "Does it work, or can it realistically work?" So: real data, real computation, tests, honest limits, a working agent loop.
- **50% Managerial model.** Problem, buyer, revenue model, go-to-market, execution ability. The Film must carry a credible business story (§14 chapters 9–11).
- Judges see it in a room, no public audience. Pitch is **12–14 min** (slot length is disputed: 15 vs 20 min in organisers' docs; design for 14 min max and keep a 12 min cut via autoplay speed).
- A previous hackathon winner faked a 3D demo. **We do the opposite: spectacular AND real.** If something is simulated, the UI labels it honestly (e.g. a "Simulated clock" badge, a "Cached run" badge). Honesty is a feature; judges who probe will find we are solid.

### 1.2 The problem (for copy and for your own reasoning)
In Dubai's hot months, midday temperatures routinely exceed 40°C, and many areas (Downtown, Marina, JLT, DIFC) are built around walkable districts where the *route you pick* decides how much direct sun you take. Existing maps optimise distance or time, never shade. Solar shade moves every minute and varies by season, so a static "shady route" doesn't exist. It has to be computed for **time and place**.

### 1.3 Who pays (managerial story, must appear in the Film)
Lead wedge (from the team): **hotels, tourism boards and hospitality; delivery companies; outdoor-worker employers.** Individuals use it free (distribution + data), B2B pays.

| Segment | Pain | Product surface | Pricing hypothesis (team to validate) |
|---|---|---|---|
| Hotels / hospitality / tourism boards | Guests complain about heat, avoid walking, miss attractions | Concierge widget ("shade-safe walks from your hotel"), white-label | Per-property monthly SaaS; tourism board = annual licence |
| Delivery / micro-mobility fleets | Rider heat stress, productivity loss, incidents | Fleet dashboard + rider app: heat-aware routing and shift pacing | Per active rider per month, or per-route API call |
| Outdoor-worker employers (construction, facilities, events) | Heat illness risk and compliance with the UAE midday work break | Crew shift planner: schedule tasks into shadier windows, flag compliance | Per site per month |
| Individuals | Heat, convenience | Free consumer app | Free (acquisition) |

**Do not invent market-size statistics.** Where the Film needs a market number, render a visible placeholder `[TEAM TO FILL — cite source]` styled as a subtle bracketed tag, and list every placeholder in `docs/OPEN_ITEMS.md`.

---

## 2. Non-negotiables

1. **Real computation.** Sun position, shadow raster, per-edge exposure, time-dependent routing and the departure optimiser are all real code on real OSM data, with tests.
2. **Every number shown to a user comes from computed output** (never from the LLM's imagination, never hard-coded). See §11.4 "token-resolved numbers".
3. **Offline-safe demo.** The whole experience (Film + App + agent in replay mode) runs on `localhost` with **no internet**. Only the live Claude calls and optional live weather need network, and both have recorded fallbacks. A demo must never die in front of judges.
4. **Deterministic Film.** Every chapter is a pure function of its local time `t∈[0,1]`. Scrubbing forward/backward must always render the same frame. No `setTimeout`-driven animation.
5. **Honest limits.** Shade from buildings and mapped trees only; awnings, unmapped trees and wind are not modelled. Say so in the UI ("Model v1: buildings, mapped trees, covered links") and in `docs/VALIDATION.md`.
6. **Premium visual identity** per §12. A visual QA loop (§18.3) is mandatory.
7. **Never leave the repo broken.** Commit at every green gate. The last commit must start both servers cleanly with one command.

---

## 3. Product definition

### 3.1 One-liner
*"Zill is the AI agent that routes you through the shade."*

### 3.2 Core user flows
1. **Pick a city** → Zill builds it (buildings, roads, trees, covered links) from open data and shows the build.
2. **Pick a time/date** → sun position and shadows update; the whole city's shade map slides with the sun.
3. **Ask for a journey** in natural language or by clicking A→B, choosing walk / cycle / scooter → agent returns **Fastest vs Coolest vs Balanced** routes with real stats (minutes in sun, % shaded, % indoors/covered, added minutes, heat-load index).
4. **Leave later?** The agent evaluates departures over a window and recommends the best time with the evidence chart.
5. **Plan a day / a shift** (multi-stop, tourist, rider or crew) → agent orders stops, inserts indoor/AC breaks in peak sun, flags policy conflicts.
6. **Proactive replan.** On a simulated delay, closure or heat alert, the agent notices, replans, and either auto-applies (if within the user's standing permission) or asks for approval.

### 3.3 Out of scope (do NOT build)
User accounts/auth, payments, real push notifications, mobile apps, real-time traffic, indoor mall floorplan routing beyond OSM data, trees beyond mapped ones, any ML training. A "send to phone" button may exist as a visual mock **clearly labelled mock**.

---

## 4. Scope tiers and the cut-line

If time or tokens run short, **protect higher tiers first**. Finish a tier completely before starting the next.

**P0 — must exist, polished (the demo cannot happen without these)**
- Downtown Dubai data bake (buildings, roads/paths, trees, covered/indoor links)
- Sun + shadow raster engine, per-edge exposure, time-dependent routing (walk/cycle/scooter)
- Backend API + working Claude tool-using agent with streamed activity feed + replay fallback
- 3D scene (buildings, ground shade overlay, sun/sky, route rendering, camera rigs)
- Film chapters 1–7 (through "leave later") fully working
- `/app` with time slider, A→B routing, comparison stats, agent chat
- Tests listed in §18, demo runbook

**P1 — should exist**
- Film chapters 8–12 (agents, customers, proof, roadmap, close)
- Day/shift planner, proactive replan simulation with approval gate
- Persona/wedge views (hotel concierge, fleet dashboard, crew planner)
- Deck-asset exporter + backup video recorder

**P2 — only if P0+P1 are green and polished**
- Second and third pre-baked cities (see §6.6) plus the "city picker" morph in Chapter 4
- Procedural hero landmarks (Burj Khalifa tiers/spire, fountain water shader)
- Field-test evidence screen fed by `data/validation/field_test.json`

**P3 — optional garnish:** ambient audio bed (toggle, default off), dusk/night "city lights" mode, sun-path arc overlay.

---

## 5. Architecture and repository layout

```
zill/
├── CLAUDE.md                     # standing rules (provided)
├── PRD.md                        # this file
├── README.md                     # how to run (write it)
├── Makefile                      # make setup | bake | dev | test | demo | record
├── .env.example                  # ANTHROPIC_API_KEY, ZILL_MODEL, ZILL_MODEL_FAST, ZILL_REPLAY, OVERPASS_URLS
├── docs/
│   ├── DECISIONS.md  OPEN_ITEMS.md  ARCHITECTURE.md  VALIDATION.md
│   ├── RUNBOOK_DEMO.md  PITCH_STORYBOARD.md  SPEAKER_NOTES.md  PROGRESS.md
│   └── deck_assets/              # auto-generated stills + backup video
├── backend/
│   ├── pyproject.toml            # Python 3.11+, deps pinned
│   ├── zill/
│   │   ├── config.py  brand.py  geo.py        # projection + constants
│   │   ├── data/       overpass.py  overture.py(optional)  bake.py  schemas.py
│   │   ├── sun/        position.py            # pvlib wrapper
│   │   ├── shade/      heightmap.py  raymarch.py  exposure.py  cache.py
│   │   ├── routing/    graph.py  tdsp.py  modes.py  heat.py  departure.py  scenarios.py
│   │   ├── agent/      orchestrator.py  tools.py  prompts.py  verifier.py  monitor.py  replay.py  personas.py
│   │   ├── api/        main.py  routes_*.py  sse.py
│   │   └── weather/    openmeteo.py  fallback.py
│   └── tests/
├── data/
│   ├── cities/<city_id>/         # baked artifacts (committed, so demo works offline)
│   │   ├── meta.json  buildings.glb  buildings.json  trees.json  graph.json  links.geojson
│   │   └── shade/<date_id>/step_<HHMM>.png  +  exposure_<date_id>.npz
│   ├── curated/                  # hand-checked overrides: landmarks, ac_links, gazetteer
│   ├── scenarios/hero.json       # auto-selected best demo journeys (see §8.6)
│   ├── weather_cache/            # recorded weather for demo dates
│   └── validation/
└── frontend/
    ├── package.json              # Next.js App Router + TS strict
    └── src/
        ├── app/  film/  app/  embed/hotel/  (routes)
        ├── brand.ts  design/tokens.ts
        ├── three/   Scene.tsx  CityBuildings.tsx  ShadeGround.tsx  Sky.tsx  Routes.tsx  Agents3D.tsx  rigs/  post/
        ├── film/    master.ts  chapters/ch01..ch12.ts  Overlay.tsx  Presenter.tsx
        ├── app-ui/  panels, chat, planner, charts
        ├── state/   useFilm.ts  useCity.ts  useSun.ts  useAgent.ts   (zustand)
        └── lib/     api.ts  sun.ts(suncalc)  geo.ts  sse.ts
```

**Runtime shape:** `make demo` starts FastAPI on `:8000` and Next.js (production build) on `:3000`. Next proxies `/api/*` to FastAPI. No other services. No database; files + in-memory caches only.

**Stack (locked by the team):** Python backend + Next.js/React frontend. Specific libraries are listed where relevant; if a pinned version fails, pick the nearest working stable one and log it.

---

## 6. Data pipeline (`backend/zill/data`, `make bake`)

### 6.1 Coordinate system (use everywhere, in both Python and TS)
- Local metric frame, origin **`O = (lat 25.1972, lon 55.2744)`** (Burj Khalifa). Axes: **x = east, y = up, z = south** (so −z is north, matching three.js's convention of looking down −z).
- `x = (lon − lon0) · 111320 · cos(lat0)`, `z = −(lat − lat0) · 110574` (metres). Implement once in `geo.py` and mirror in `lib/geo.ts`; add a test that round-trips 1000 random points to < 0.01 m error and that Python and TS agree on 10 golden points stored in `data/curated/geo_golden.json`.
- The origin is per-city (`meta.json.origin`). Dubai uses the above.

### 6.2 City definition (Downtown Dubai)
- Core bbox (hint, tune after inspecting data): **S 25.1850, W 55.2600, N 25.2100, E 55.2900** (~2.8 × 2.8 km). Must include Burj Khalifa, Dubai Mall, Burj Lake / Dubai Fountain, Dubai Opera, Emaar Boulevard, Sheikh Mohammed bin Rashid Blvd, the Burj Khalifa/Dubai Mall metro station and its elevated pedestrian link.
- **Shadow-caster buffer:** fetch buildings in the core bbox **+ 900 m** on all sides so tall towers outside the core still cast shadows in. Routing/graph and the rendered scene use only the core bbox (+ 100 m margin).
- Gazetteer hints (approximate, ±200 m; **resolve by name via Overpass and log the resolved coordinates**; snap to nearest graph node): Burj Khalifa (25.1972, 55.2744), The Dubai Mall (25.1985, 55.2796), Dubai Fountain (≈25.1950, 55.2795), Dubai Opera (≈25.1962, 55.2713), Burj Khalifa/Dubai Mall Metro Station (≈25.2010, 55.2697), Souk Al Bahar (≈25.1930, 55.2760), Burj Park (≈25.1925, 55.2735), Address Downtown, Armani Hotel Dubai, Palace Downtown, Boulevard Plaza.

### 6.3 Sources and fetching
- **Primary: OpenStreetMap via Overpass API.** Endpoints in `OVERPASS_URLS` (default list: `https://overpass-api.de/api/interpreter`, `https://overpass.kumi.systems/api/interpreter`). Retry with exponential backoff, rotate mirrors, respect rate limits, **cache raw responses** under `data/raw/` (git-ignored) so re-bakes are instant.
- Fetch in tiles (e.g. 4 × 4) to avoid timeouts, then merge/deduplicate by OSM id.
- Queries (conceptually): `way/relation["building"]`, `["building:part"]`, `way["highway"]` (walkable + cyclable subsets), `node["natural"="tree"]`, `way["natural"="tree_row"]`, `way["covered"]`, `way["tunnel"="building_passage"]`, `way["indoor"]`, `way["layer"]` with `bridge`, `node["highway"="bus_stop"]`, `node["railway"="station"]`, `node["amenity"~"cafe|restaurant|drinking_water|bench"]`, `way["shop"="mall"]`, `way["leisure"="park"]`.
- Optional enhancement (P2 only): Overture Maps buildings for heights, if easily available offline. **Not required.**

### 6.4 Building heights (rules, in priority order)
1. If a `building:part` set exists inside a building, **use the parts** (with their own heights) and drop the outer shell to avoid double-counting.
2. `height` tag (parse "m", "ft", plain numbers). Also honour `min_height`.
3. `building:levels` × **3.4 m** (+ `roof:levels` × 3.0 m).
4. Fallback by tag: `building=apartments|residential` 30 m, `hotel` 45 m, `commercial|office` 40 m, `retail|mall` 22 m, `garage|parking` 12 m, default **18 m**.
5. `data/curated/landmarks.json` overrides always win. Must include **Burj Khalifa = 828 m** (if OSM already models it correctly via parts, keep OSM and just assert total height ≈ 828 ± 5 m in a test).
- Emit stats to `meta.json`: counts by height source (tag / levels / fallback). Show these in `docs/VALIDATION.md` (honest data-quality reporting).

### 6.5 Walkable/cyclable graph
- Build from OSM ways with these classes: **footway, pedestrian, path, steps, living_street, residential, service (non-private), tertiary/secondary/primary (walk allowed unless `foot=no`), cycleway, track**, plus **crossings** as nodes. Respect `access`, `foot`, `bicycle` tags. Split ways at intersections. Keep `highway`, `surface`, `lit`, `bridge`, `tunnel`, `layer`, `covered`, `indoor`, `name` per edge.
- Per-edge attributes written to `graph.json` (columnar, compact): `u, v, length_m, geometry (local metres), highway, flags{covered, indoor, ac_link, stairs}, allowed{walk,cycle,scooter}`.
- **Mode rules:** walk = all pedestrian-allowed; cycle = cycleways + roads (not motorway/trunk) + footways only where `bicycle=yes|designated`; scooter = same as cycle in v1 (document: "UAE e-scooter lane rules simplified in v1"). Speeds: walk **1.4 m/s**, cycle **4.5 m/s**, scooter **5.0 m/s**; stairs ×0.5 speed for walk, forbidden for cycle/scooter; a crossing adds **8 s** wait for walk, **10 s** for cycle/scooter (constant; configurable).
- Keep the largest connected component per mode; log dropped components.

### 6.6 Covered and air-conditioned links (this is Dubai's secret weapon)
Classify each edge into one of: `open`, `covered` (arcade/canopy/overpass above), `indoor` (inside a building), `ac_link` (enclosed air-conditioned bridge or mall passage).
- `covered=yes|arcade|colonnade` or `tunnel=building_passage` → `covered` (sun fraction 0).
- Edge midpoint inside a building polygon **and** `highway` in (footway, corridor, pedestrian, path) or `indoor=*` → `indoor`.
- Elevated enclosed links (e.g. the Burj Khalifa/Dubai Mall metro pedestrian link): if OSM tags them `covered=yes`/`indoor=*` → `ac_link`; else use `data/curated/ac_links.geojson`, which **you draft from OSM geometry by name and mark `"verified": false`**; list unverified items in `docs/OPEN_ITEMS.md` for the humans to confirm on site.
- Indoor/AC edges: sun fraction 0, **comfort multiplier** 0.1 (cooler), **crowd/time penalty** 1.15 on length (mall traffic). Configurable constants in `routing/modes.py`.
- Entrances: only allow transitions between `outdoor` and `indoor` at nodes tagged `entrance=*` or at curated entrance nodes; if none found inside a given mall, create a conservative curated set and log it.

### 6.7 Trees
- `natural=tree` points: canopy radius = `diameter_crown/2` if tagged else **3.0 m**; height = `height` tag else **7.0 m**; **canopy transmissivity 0.35** (65% of sun blocked). Rasterised as shade cells with partial sun fraction. `tree_row` ways: sample trees every 6 m.
- State plainly in docs: OSM trees in Dubai are incomplete; Zill under-estimates shade from trees (conservative).

### 6.8 Bake outputs (committed to git, small enough to commit; target < 150 MB total, compress PNG; if larger, tell me in `OPEN_ITEMS.md` and use git-lfs)
- `buildings.glb` — triangulated extrusions (earcut / trimesh), one mesh per 250 m tile, per-vertex `_building_id`, `_height`, footprint holes handled, flat/hip roofs not needed (flat is fine). Y-up, local metres.
- `buildings.json` — footprints + heights + ids + names + source flags (used by shade engine and UI picking).
- `trees.json`, `graph.json`, `links.geojson`, `meta.json` (origin, bbox, counts, source timestamp, OSM licence attribution string "© OpenStreetMap contributors").
- Display attribution on every screen footer (ODbL requirement).

### 6.9 Additional cities (P2 only)
Pre-bake **Abu Dhabi (Corniche/Marina Mall area)**, **Dubai Marina**, and one non-UAE hot city (**Singapore Marina Bay** or **Doha West Bay**) with the same pipeline (~1.5–2 km boxes to keep bakes fast). The pipeline MUST take only `{city_id, name, bbox, origin, timezone}` as config; **no city-specific code** (Dubai's landmark/link overrides live in `data/curated/<city_id>/`, optional). A test bakes a tiny synthetic bbox to prove city-agnosticism.

---

## 7. Sun and shadow engine (`backend/zill/sun`, `backend/zill/shade`)

### 7.1 Sun position
- `pvlib.solarposition.get_solarposition` (or `astral` if pvlib is a problem) with timezone `Asia/Dubai` (UTC+4, no DST). Output: altitude, azimuth (degrees, azimuth clockwise from north).
- Frontend uses `suncalc` for the live slider light and sky. **Test:** backend vs `suncalc`-equivalent values agree within 0.5° for 20 sample timestamps (store goldens in `data/curated/sun_golden.json` generated from pvlib; the TS test compares against them).
- Sanity tests: Dubai on 21 June at solar noon altitude ≈ 88°; on 21 December ≈ 41°; sunrise/sunset times within 3 min of pvlib.
- **Sun direction vector** (local frame: east = +x, north = −z, up = +y). The unit vector pointing **toward the sun** is `(sin(az)·cos(alt), sin(alt), −cos(az)·cos(alt))`, with azimuth clockwise from north. Unit test: az=90° (sun due east) → +x; az=0° (due north) → −z.

### 7.2 Heightmap
- Rasterise buildings (and tree canopies) into a float32 height grid, **cell size `GRID_RES_M = 2.0`**, covering core bbox + 900 m buffer (caster area). Use `rasterio.features`/`skimage.draw.polygon`/numba-accelerated scanline fill, your choice. Buildings use footprint height; trees use canopy discs with transmissivity channel (separate float32 `canopy_block` grid in [0, 0.65]).
- Keep `ground_mask` (walkable area) separate from building mask.

### 7.3 Shadow raymarch (numba, parallel)
For every output cell `p` (core area only), march toward the sun in the horizontal direction `(sin az, −cos az)` (in grid space), step `s = GRID_RES_M`, up to `MAX_SHADOW_M = 1500` (also stop when the ray's height `h0 + k·s·tan(alt)` exceeds `max_height_in_scene`). Cell is **shaded by buildings** if for some step `k`, `H[p + k·s·dir] > h0 + k·s·tan(alt)`, where `h0 = 1.5 m` (pedestrian body height above ground, ignoring terrain; Downtown is flat). Trees: accumulate `1 − Π(1 − block_i)` along the ray when the ray passes beneath canopy height.
- Output `sun_fraction` as `uint8` 0–255 (0 = fully shaded, 255 = full sun). Cells inside building footprints = 0 (not walkable) and flagged in a separate mask.
- When `alt ≤ 2°` → treat all outdoor cells as **no direct sun** (`sun_fraction = 0`) and mark `is_night_or_twilight`.
- **Softening:** apply a tiny 3×3 blur or compute with a sun-disc angular size (0.53°) by sampling 3 alt/az offsets and averaging, so shadow edges are soft and not jaggy. Required: results must look good when rendered as a texture.
- Performance targets: one 10-minute step for a ~1300×1300 grid ≤ **2.5 s** with numba on a laptop; if slower, vectorise the "sweep" formulation (propagate shadow height along the sun direction, O(N)) and note it in DECISIONS.md.
- **Tests (must pass):** (a) lone 100 m flat-roof box, sun alt 45° → shadow length 100 ± 3 m, in the right direction for az=90, 180, 270; (b) sun alt 90° → shadow only on the footprint; (c) two boxes with gap → gap is shaded only when geometry says so; (d) symmetry test: rotating the scene 90° and sun azimuth 90° gives the rotated raster.

### 7.4 Time grid and caching
- **Time step: 10 minutes**, from civil sunrise − 20 min to sunset + 20 min (approx. 05:40–19:00 in Dubai, depends on date). Index steps by `HHMM`.
- **Preset dates** (precomputed in `make bake`): `2026-01-15` (winter), `2026-04-15` (spring), `2026-07-15` (peak summer), `2026-10-24` (hackathon Saturday). IDs: `winter`, `spring`, `summer`, `hackathon`.
- Any **other date**: compute on demand when requested via API (≈79 steps × ≤2.5 s, run in a background thread pool, stream progress; the first requested step is computed first so the UI is responsive; cache to disk under `data/cache/`). The UI shows "Computing shade for 3 Mar…" with a progress bar.
- Per-preset artifacts: `shade/<date_id>/step_<HHMM>.png` (8-bit grayscale, lossless, for the frontend ground overlay and for debugging) and `exposure_<date_id>.npz` (float16 `[n_edges, n_steps]` exposure fraction per edge).

### 7.5 Per-edge exposure
- For each graph edge, sample points every **3 m** along its geometry (at least 2 samples), bilinear-sample `sun_fraction`, average → `exposure ∈ [0,1]` per step. Edges flagged `covered/indoor/ac_link` → 0 regardless of raster. Edges whose samples fall inside building footprints but are not tagged indoor (digitising noise) → use nearest outdoor value within 3 m (log how often).
- Store per-step arrays; routing looks up by **arrival time**, linearly interpolating between the two nearest steps.

---

## 8. Routing engine (`backend/zill/routing`)

### 8.1 Cost model
For edge `e`, mode `m`, traversal starting at clock time `τ`:
```
t_e      = length_e / speed_m  (+ crossing wait, stairs factor)   # seconds
sun_e(τ) = exposure of e at time τ                                # 0..1
w_m      = sun weight: walk 1.0, scooter 0.85, cycle 0.8          # riders move faster; wind
cost_e   = t_e · ( 1 + λ · w_m · sun_e(τ) · uv(τ) ) · comfort_e · crowd_e
```
- `λ` is the **coolness preference** (0 = fastest, 1.0 = balanced default, 3.0 = coolest). Three canonical routes are always produced: **Fastest (λ=0)**, **Balanced (λ=1.0)**, **Coolest (λ=3.0)**; the agent may request any λ.
- `uv(τ)` = simple multiplier from solar altitude: `clip(sin(alt)^0.6, 0.15, 1.0)` so low evening sun hurts less. (Document as heuristic.)
- `comfort_e` = 0.1 for `indoor`/`ac_link` (cool), 0.5 for `covered`, 1.0 otherwise. `crowd_e` = 1.15 for indoor, 1.0 otherwise. (Applied to the *penalty term*, not to travel time; keep time and discomfort separate in code.)
- **Never let cost go below pure travel time** (heuristic admissibility).

### 8.2 Algorithm
- **Time-dependent A\*** (FIFO property holds because speed is constant and exposure only changes the penalty, not the traversal time). Heuristic: Euclidean distance / `speed_m`. Priority queue via `heapq`. Return full path with **per-vertex arrival timestamps**.
- Must answer a typical Downtown query in **< 300 ms** (graph ≈ 20–40k edges). Profile; vectorise exposure lookups (precomputed `[edges, steps]` arrays; interpolate per edge on demand).

### 8.3 Route statistics (all computed, never estimated by the LLM)
For each route return:
`distance_m, duration_s, sun_exposure_s` (time-weighted sum of `sun_e·t_e`), `shaded_pct` (by time), `covered_pct`, `indoor_pct`, `heat_load_index (RHL)`, `added_time_s` vs fastest, `sun_saved_s` vs fastest, `sun_saved_pct`, `segments[]` with `{geometry, arrival_s, sun_e, class}` for rendering, and `elevation`-free 2D geometry in local metres + WGS84.
**Relative Heat Load (RHL)** = Σ t_e · (sun_e·1.0 + (1−sun_e)·0.35) for outdoor edges, + Σ t_e·0.1 for indoor/AC edges. Presented as an index with label "model estimate, not a measurement". Also give `rhl_saved_pct` vs fastest.

### 8.4 Departure-time optimiser (`departure.py`)
Given origin, destination, mode, window `[t0, t1]` (default now → +90 min), step 5 min, evaluate **Balanced route per departure time**; return the table `[{depart, duration_s, sun_exposure_s, shaded_pct, rhl}]`, plus a recommendation by minimising `rhl + μ·wait_s` with `μ` default 0.25 (waiting has a cost) and constraint `latest_arrival` if given. Output a human-checkable **"why"** struct: which segments change shade state between departure A and B (e.g. "Boulevard east side falls into tower shadow after 15:10").
- Use a thread pool; total ≤ 3 s for 19 departures.

### 8.5 Multi-stop planner (`planner.py`, P1)
Input: ordered/unordered stops with dwell times, time windows, mode, start time. Algorithm: for ≤ 8 stops, **enumerate permutations** (or DP/beam search above 7) using time-dependent route costs (cache pairwise costs per departure bucket); insert **"cool-down"** breaks (nearest `indoor`/`ac_link`/café node) when cumulative RHL over a rolling 30 min exceeds `RHL_BREAK_THRESHOLD` (default tuned so that peak-sun walks trigger it; expose the constant). For `crew` persona, also place work blocks in lowest-exposure windows and mark **policy conflicts** (see §16.3).

### 8.6 Hero scenario auto-selection (`scenarios.py`)  ← important
The Film's money shots must be real *and* dramatic. Don't hand-pick coordinates; **search for them**:
1. For all pairs (A,B) from the gazetteer (≥ 12 POIs) with 400–1500 m straight-line separation, for departure times in {12:30, 13:30, 14:30, 15:30} on the `summer` and `hackathon` dates, for walk (and cycle for a rider scenario), compute Fastest vs Coolest.
2. Rank by `sun_saved_s` subject to `added_time_s ≤ 25% of fastest` and coolest route not absurd (detour ratio ≤ 1.35).
3. Write top candidates to `data/scenarios/hero.json` with fields `{id, persona, mode, origin{name,lat,lon}, dest{...}, date_id, depart, fastest{stats}, coolest{stats}}`. Select **three**: `tourist_walk` (hero, ideally uses an `ac_link` or covered route), `rider_cycle`, `crew_shuttle` (short, high exposure).
4. The Film and App "Try the hero journey" buttons read from this file. If the best `sun_saved_s` for the hero is **< 90 s** at summer peak, widen the gazetteer and search again; log what you tried. **Do not fabricate a better result.** If the real result is modest, the Film says so honestly and leans on the departure-time optimiser and the AC link story.

---

## 9. Weather and heat context (`backend/zill/weather`)
- **Open-Meteo** (no key): temperature, apparent temperature, humidity, UV index, wind for the city's lat/lon, hourly. Cache responses to `data/weather_cache/` and **ship recorded files** for each preset date (`winter`, `spring`, `summer`, `hackathon`; for `summer` and others, record a realistic recorded profile if live archive data isn't reachable, and **label the file `"synthetic_representative": true`**, shown in the UI as "Representative summer profile").
- `weather.get(city, datetime)` returns live → cache → recorded fallback, with a `source` field the UI can show.
- Weather feeds: (1) context shown in UI and agent prompts, (2) a `heat_alert` flag if apparent temp ≥ 40°C or UV ≥ 8 (used by the agent's proactive monitor and the crew policy pack). Weather does **not** change shadow geometry.

---

## 10. Backend API (FastAPI, async, CORS for localhost, OpenAPI docs at `/docs`)

All responses JSON unless noted. All times ISO-8601 with `+04:00`. Positions are `{lat, lon}`; local metre coordinates are included wherever the frontend renders.

| Method & path | Purpose |
|---|---|
| `GET /api/health` | liveness, model availability, replay mode flag |
| `GET /api/cities` | list baked cities `{id,name,origin,bbox,counts,status}` |
| `GET /api/cities/{id}/meta` | meta.json |
| `GET /api/cities/{id}/files/{name}` | static baked assets (glb/json/png) with long cache headers |
| `POST /api/cities/build` | SSE stream: build a city from a name or bbox. Steps and **real counts**: `geocode → fetch_buildings → fetch_roads → fetch_trees → heights → graph → covered_links → shadow_precompute → ready`. If the city is already baked, **replay the recorded build log at real timing and label it `cached`**; if `?live=1` and network works, run for real on a small bbox (≤ 1.2 km²) and label `live`. |
| `GET /api/sun?city&at=` | altitude, azimuth, sunrise, sunset, vector |
| `GET /api/shade/{city}/{date_id}/{HHMM}.png` | ground shade raster for the 3D overlay |
| `POST /api/shade/compute` | request on-demand date; SSE progress |
| `POST /api/route` | `{city, mode, origin, dest, depart_at, lambdas?:[0,1,3]}` → routes `{fastest,balanced,coolest}` with stats + segments |
| `POST /api/departure` | `{...route, window}` → table + recommendation + "why" |
| `POST /api/plan` | multi-stop planner (P1) |
| `GET /api/weather?city&at=` | weather w/ source |
| `GET /api/gazetteer/{city}?q=` | place search (local gazetteer first, Nominatim fallback if online) |
| `POST /api/agent/session` | create session `{persona, city, date_id, clock, autonomy_level}` |
| `POST /api/agent/message` | SSE stream of agent events (see §11.3) |
| `POST /api/agent/approve` | approve/reject a pending plan or replan |
| `POST /api/agent/simulate` | inject event `{type: delay|closure|heat_alert|sun_clock_jump, params}` into the session's simulated clock (powers the proactive-replan demo) |
| `GET /api/scenarios/{city}` | contents of `hero.json` |

Standards: Pydantic v2 models for every request/response; request IDs; structured logs; typed errors; no stack traces to the client. SSE events are newline-delimited `event:`/`data:` JSON.

---

## 11. The Agent (this is where the "AI Agents" points are)

The product is not "a router with a chatbot". The agent **owns a goal over time**, uses tools, verifies its own claims, asks for approval at the right moments, and acts proactively.

### 11.1 Models and keys
- Anthropic Python SDK. Env: `ANTHROPIC_API_KEY`, `ZILL_MODEL` (default `claude-sonnet-5-5`, the main reasoning/tool-use model), `ZILL_MODEL_FAST` (default `claude-haiku-5-5`, for cheap sub-calls such as narration drafts/intent). Verify the model IDs against current Anthropic docs at runtime start (`/api/health` reports which are reachable); if a model ID 404s, fall back down the list `[claude-sonnet-5-5, claude-opus-5-5, claude-haiku-5-5]`.
- The key lives **only** in backend env; never sent to the browser.
- If no key / no network / `ZILL_REPLAY=1` → **Replay mode** (§17).

### 11.2 Agent roles (one orchestrator, specialised passes)
1. **Planner (tool-use loop).** Understands the user's goal and persona in natural language ("I'm walking from the metro to the Opera, I tire easily in heat", "I have 6 drop-offs between 1 and 4 pm on a scooter", "my crew needs to finish 5 tasks around the Boulevard this afternoon"). Calls tools, compares options, drafts a proposal.
2. **Verifier (separate call, separate system prompt).** Receives the draft plan + the raw tool outputs and checks: every claim is supported, every number is a resolved token, no unreachable/invalid edge, constraints respected (arrival window, mode rules, policy pack). Returns `pass` or a list of defects; Planner must fix and resubmit (max 2 rounds). The activity feed shows the Verifier explicitly: "Verifier: 14 claims checked, 14 supported."
3. **Monitor (proactive loop).** Runs on the session's **simulated clock** (default ×60, 1 real second = 1 sim minute; presenter can jump). Each tick it re-evaluates the active plan against current conditions (injected delays, closures, heat alerts, sun position). If the plan's expected RHL or arrival changes beyond thresholds, it calls the Planner to **replan**, then applies the **autonomy policy** (11.5).
4. **Narrator.** Turns structured results into short, human, persona-appropriate text (tourist: warm and simple; rider: terse and tactical; crew lead: operational and compliance-aware).

### 11.3 Streaming activity feed (event schema)
Server → client SSE `agent` events, each `{id, ts, type, payload}` with types:
`session_started`, `thought` (a *summary* of reasoning for display, not raw chain-of-thought), `tool_call {name,args}`, `tool_result {name,summary,duration_ms}`, `verifier {checked, passed, defects[]}`, `proposal {plan_id, routes[], recommendation, tokens}`, `approval_request {plan_id, risk, options}`, `plan_committed`, `monitor_tick {sim_time, status}`, `replan {reason, diff}`, `message {text, resolved}` (final user-facing text), `error`.
The UI renders this feed as a refined timeline (no terminal-green nonsense, see §12), and the Film's Chapter 6/8 reuse the same component.

### 11.4 Token-resolved numbers (anti-hallucination, a headline technical feature)
- Tools return structured results with stable paths (e.g. `route.coolest.sun_exposure_s`).
- The Planner/Narrator must write user-facing text with **tokens** like `{{route.coolest.sun_saved_min}}`, `{{departure.best.depart_time}}`, never literal digits for computed facts. The backend **resolves tokens** from the tool-result store before sending `message`. Unresolved tokens → automatic retry; regex check rejects any remaining numeric claim not coming from a token or the user's own input (allow clock times/years from the user and ordinal words).
- Formatting helpers: `_min` (seconds → minutes, 1 decimal), `_pct`, `_time` (HH:MM Gulf time), `_m`.
- Test: a fuzz test feeding adversarial model outputs containing bare numbers must be rejected or rewritten.

### 11.4b Prompts
Write `prompts.py` with clear, versioned system prompts for each role: persona definitions; token rules; tool-use guidance ("always compare at least Fastest vs Coolest; always run the departure optimiser when the departure time is flexible; prefer AC links in peak heat when added time ≤ 25%"); safety/health framing ("Zill reduces sun exposure; it is not medical advice; in heat alerts recommend hydration and shade breaks"); refusal to fabricate unavailable data; instruction to **say when the model's limits matter** (trees, awnings).

### 11.5 Autonomy levels (user-selectable, shown in UI as a three-stop control)
- **L1 Advisor:** only suggests; never changes plans.
- **L2 Planner (default):** builds full plans, orders stops, proposes departure times; **asks approval** before committing.
- **L3 Autopilot:** after a plan is approved, the Monitor may **auto-apply small replans** (|Δarrival| ≤ 10 min and RHL not worse than +10%); anything larger requires approval. Every autonomous action is logged with a reason and is **reversible** ("Undo").

### 11.6 Tools (JSON-schema'd, deterministic, unit-tested; each returns `{ok, data, summary}`)
`resolve_place(query)`, `get_sun(at)`, `get_weather(at)`, `plan_route(origin,dest,mode,depart_at,lambda)`, `compare_routes(origin,dest,mode,depart_at)`, `optimise_departure(origin,dest,mode,window,latest_arrival?)`, `find_cool_stops(near,radius,type)`, `plan_day(stops,mode,start,persona)`, `check_policy(plan,policy_pack)`, `commit_plan(plan_id)`, `simulate_clock(ts)` (internal), `get_active_plan()`, `explain_segment(segment_id)` (why this segment is shaded: names the casting building/time window; derive by sampling which building blocks the ray at that cell), `build_city(query)` (invokes the pipeline for the Chapter-4 demo; non-destructive).
- Rate/size limits: ≤ 12 tool calls per turn; per-tool timeout 8 s; errors returned as data so the agent can recover.

### 11.7 Personas and policy packs
`tourist`, `rider` (delivery), `crew` (outdoor work). A **policy pack** is a JSON of rules the Verifier enforces. Ship a `UAE_OUTDOOR_WORK` pack: no outdoor work in direct sun during the **12:30–15:00 midday window between 15 June and 15 September** (team: **verify the current rule** before the pitch; mark `"verified": false` in the file and in the UI as "Policy pack: UAE midday break (v1, verify)"), plus break-frequency rules as configurable constants. Never present it as legal advice.

---

## 12. Frontend design system (read twice)

### 12.1 Mood
Premium, rich, cinematic, restrained. **A luxury architecture film, not a hackathon dashboard.** Warm desert light, matte stone, brushed metal, deep shadows, generous negative space. Motion is slow, eased, weighty. Typography does the talking.

### 12.2 Hard bans
No neon (no cyan/magenta/electric-blue/lime), no purple-blue AI gradients, no glassmorphism blur-cards, no glowing grid floors, no "sparkle" icons, no emoji, no hexagons/circuit-board textures, no stock robot imagery, no terminal-green text, no drop-shadow-heavy cards, no lens flares, no chromatic aberration. Bloom only extremely subtle and only on the sun and warm window lights at dusk.

### 12.3 Tokens (`design/tokens.ts`, mirrored as CSS variables)
| Token | Hex | Use |
|---|---|---|
| `ink` | `#0E0C0A` | page background, deepest shade |
| `umber` | `#1A1511` | panels |
| `stone` | `#2A231C` | hairlines on dark, building base at night |
| `sand` | `#D8C7A3` | primary light text accents, ground in sun |
| `champagne` | `#E9DCBC` | headlines on dark |
| `ivory` | `#F4EEE1` | body text on dark |
| `bronze` | `#A06A3B` | secondary accents |
| `brass` | `#C8A15A` | the **coolest route** line, key highlights |
| `ember` | `#D07A35` | **sun-exposed** segments |
| `clay` | `#9C4F3B` | heat warnings |
| `shade` | `#22333A` | **shaded** ground (deep desaturated teal-slate) |
| `oasis` | `#5E8C7B` | AC links, covered, "cool" state (muted sage) |
| `slate` | `#7C8A94` | the **fastest route** (neutral, deliberately unexciting) |
Exposure ramp for lines/ground: `shade → #6F6A55 → ember` (via perceptual interpolation, e.g. OKLab).

### 12.4 Typography
Display: a high-contrast serif (**Fraunces** or **Cormorant Garamond**, via `next/font`, self-hosted at build so no runtime network). Text/UI: **Inter Tight** or **Manrope**. Numerals: tabular lining in HUD. Sizes: hero 9–14 vw serif light; section titles 3–5 vw; body 15–18 px; HUD numerals 28–44 px. Letter-spacing slightly open on small caps labels (`0.18em`). Hairline rules 1 px at 12% ivory.

### 12.5 Motion and filmic treatment
- Easing: `cubic-bezier(0.22, 0.61, 0.36, 1)` default; camera moves use `power2.inOut`; no bounce, no springs on cinematic elements.
- Post-processing (R3F postprocessing): ACES/AgX tone mapping, **very subtle** bloom (threshold high), SSAO (low), vignette (0.25), fine film grain (opacity ≤ 0.06), gentle depth of field in hero shots only. Quality tiers (`high|medium|low`) auto-selected by a quick GPU/FPS probe; `?q=low` forces low.
- Colour grading by time of day: dawn (rose-gold/low blue), noon (bleached warm white, strong contrast), golden hour (amber), dusk (deep blue-umber with warm windows). Implement as uniform-driven LUT-like curves in a custom post pass.
- Sky: physically inspired gradient driven by sun altitude (Rayleigh-style), a soft sun disc, faint haze at horizon; **no photographic skybox needed**.
- Heat shimmer (Chapter 2) as a very subtle screen-space distortion over the ground only.

### 12.6 UI components (all in tokens)
Command bar (centre bottom in Film, top in App): serif placeholder text, hairline underline, caret in `brass`. Chips with hairline borders. Panels: solid `umber` at 92% opacity, no blur. Charts (visx/d3): hairline axes, `brass`/`ember`/`shade` fills, direct labelling instead of legends. Activity feed: each event is a one-line row with a small colour-coded marker (tool = bronze, verifier = oasis, replan = ember), timestamps in tabular numerals.

---

## 13. The 3D scene (`frontend/src/three`)

Stack: `three`, `@react-three/fiber`, `@react-three/drei`, `@react-three/postprocessing`, `zustand`, `gsap`, `lenis`, `suncalc`, `visx` or `d3`, `framer-motion` (UI only), Tailwind. One persistent `<Canvas>` shared by `/film` and `/app` (different state/rigs).

### 13.1 City layers
1. **Buildings:** load `buildings.glb` (drei `useGLTF`). Material: matte warm stone (`MeshStandardMaterial`/custom), roughness 0.85, subtle per-building tint variation from `_building_id` hash (±4% lightness, warm hues only), a faint vertical-window-line procedural shader (very low contrast; at dusk windows get warm tungsten emissive on ~35% of floors by hash). Roofs slightly lighter than walls. Ambient occlusion baked into vertex colours near the ground if cheap. Frustum culling per tile. Target ≤ 400 draw calls.
2. **Ground:** large plane in `ink`/`stone` + roads/paths drawn as slightly lighter ribbons from `graph.json` (thin, flat, matte). Parks as muted `oasis` at 25% saturation. Water (Burj Lake): flat, very dark, subtle moving normal map (P2 shader).
3. **Shade overlay (`ShadeGround.tsx`) — the authoritative visual of the product.** Load `step_<HHMM>.png` rasters as textures; shader blends the two nearest steps by time fraction (smooth scrubbing), maps `sun_fraction` to colour: shade `#22333A`@ high opacity → ground sand in sun. Edges of shadow slightly soft. Overlay uses the **same raster** that routing uses (so the picture and the numbers cannot disagree). Prefetch ±3 steps; show nothing but a soft fade while loading (no pop).
4. **Real-time shadow map** for building-on-building and tree shadows near the camera: one `DirectionalLight`, shadow camera fitted to a ~600 m box around the camera focus, 4096 map, PCF soft. Light direction from `lib/sun.ts`. **The raster is truth for stats; the shadow map is decoration** — verify they visually agree for the 12:00 and 16:00 hackathon frames in a QA screenshot.
5. **Trees:** instanced low-poly canopies (muted sage/olive, slight sway-free), from `trees.json`.
6. **Covered/AC links:** rendered as thin `oasis` ribbons/volumes with a faint inner warm glow; labelled on hover/Film highlight.
7. **Routes (`Routes.tsx`):** a tube/ribbon 0.8–1.2 m wide hugging the ground (+0.15 m), per-vertex colour by exposure (shade→ember ramp) for the **analysis view**; in **presentation view** the Fastest route is `slate`, the Coolest is `brass` with a slow travelling highlight (a moving soft pulse along the line, not a blinking dot). A small marker (a simple warm sphere/ring) represents the traveller, with the **time-of-arrival clock** moving the sun (optional "sun follows traveller time" toggle).
8. **Sky/Sun (`Sky.tsx`):** per §12.5. The sun's disc is placed in the sky at the true azimuth/altitude (so shadows visibly "point away").
9. **Landmarks (P2):** procedural Burj Khalifa (three-lobed tower, spiral setbacks, spire, total height 828 m) used **only if the OSM mesh looks wrong**; fountain pool with gentle water motion.

### 13.2 Camera rigs (`rigs/`)
- `OrbitRig` (slow orbit around a target with altitude drift), `DollyRig` (A→B straight with easing and optional look-at track), `CraneRig` (rise + tilt), `FlyRig` (follows a `CatmullRomCurve3`, lookahead 25–40 m, banking ≤ 4°, height 2–60 m configurable, **speed profile eased**), `TimeRig` (camera static, sun time animated).
- All rigs are **pure functions** `(t, params) → {position, target, fov, roll}`; the Film's chapter files compose them. FOV 28–45° (cinematic, longer lenses for hero shots; avoid wide fisheye feel). Add a subtle handheld-free "float" (≤ 0.15 m low-frequency noise seeded, so deterministic).
- Collision-avoidance for `FlyRig` is not required; instead, **author fly-through heights** per route segment so the camera stays above rooftops when the route goes through a mall (cut to an interior-style low-key "AC link" shot: slight cool grade shift to `oasis`, dimmer, then back out).

### 13.3 Performance and robustness
- 60 fps target at 1080p on a recent laptop GPU; auto-downgrade DPR and post effects if the rolling frame time > 22 ms for 2 s. `?debug` shows an FPS/draw-call overlay.
- Pre-load everything behind a **refined loading screen** ("Preparing Downtown Dubai…" with a thin brass progress line, no spinner clichés) so the Film never pops in.
- WebGL context loss handler; fallback static hero image per chapter (generated by the deck exporter) so a GPU problem degrades to stills instead of a blank page.
- Everything must work in Chrome/Edge latest and Safari latest.

---

## 14. THE FILM — `/film` (the pitch visuals)

### 14.1 Mechanics
- **One tall scroll container**; scroll position → `progress ∈ [0,1]` → master timeline (total nominal **780 s = 13:00**, defined as the sum of chapter durations in `film/master.ts`). Smooth scroll via **Lenis**; scrubbing is deterministic (§2.4).
- **Autoplay:** `Space` toggles autoplay (advances progress at real-time speed × `speed`, default 1.0). `[` / `]` change speed in steps of 0.05 between 0.85× and 1.15× (so the same film can run 11:30–15:20). `←/→` jump to previous/next chapter (smooth, 1.2 s). `1`–`9`,`0`,`-`,`=` jump to chapters 1–12. `Esc` pauses. `F` fullscreen. `T` toggles a tiny elapsed-time/chapter indicator (hidden by default so judges don't see it). `H` hides all UI chrome. `L` toggles low-quality mode.
- **Presenter mode** (`/film?presenter=1`, for a laptop screen): a second window or panel is not required; instead, a compact, toggle-able strip at the bottom shows chapter name, elapsed vs target time, and the next chapter's first talking point (from `SPEAKER_NOTES.md` embedded at build). Off by default.
- **Live hand-off:** the last chapter has a "Try it live" action that routes to `/app` preserving city/date state. Also a keyboard shortcut `A` to jump to `/app` at any time (and `Backspace` in `/app` to return to the Film at the last chapter), so the presenter can answer questions interactively.
- Real data everywhere: the city is the real baked Downtown; the route stats come from `hero.json`; the agent feed in Ch. 6/8 is a **real recorded agent session** played back from `backend/replay/` with true tool names and outputs, badged "Recorded session" (and Ch. 6 can instead run **live** if `?live=1` and the agent is reachable).
- On-screen text is sparse (the presenter speaks): chapter title cards in serif, short single-line captions (≤ 12 words), HUD numerals. **No paragraphs.** Captions fade in/out with the beat, positioned with generous margin (lower-left or lower-centre).

### 14.2 Chapters (durations sum to 780 s)
Camera numbers are *starting points* in the local frame (metres, origin at the Burj; x east, y up, z south). Tune them through the visual QA loop (§18.3) until each shot is composed like a film frame: strong foreground/background layering, rule-of-thirds, long lens, atmospheric haze. Where a camera number conflicts with good composition, composition wins.

| # | Title (card) | Dur | Beat |
|---|---|---|---|
| 1 | **"Dubai, 13:00."** | 40 s | Black → pre-dawn blue-umber, skyline silhouette appears as light rises (time 05:40 → 07:10 on the `hackathon` date at 6× speed, sun disc breaking the horizon). Slow `CraneRig`: start (−2400, 90, 3000) looking at (0, 300, 0), rise and glide to (−1100, 220, 1500). Title in champagne serif: *Zill*, then the one-liner. Caption: "The sun is the first thing you plan around." |
| 2 | **"The problem."** | 50 s | Cut to street level on the Boulevard at 13:30 `summer`: hard bleached light, heat shimmer on ground. A traveller marker walks the **fastest** route (slate); the sun-exposure HUD ticks up in `ember` (e.g. "9.4 min in direct sun", value **from `hero.json`**). Captions: "Maps optimise for time." / "Nobody optimises for shade." Placeholder tag where a heat-stat would go: `[TEAM TO FILL — cite source]` if used. |
| 3 | **"Shade moves."** | 55 s | `TimeRig`: high 3/4 view of Downtown; sun time-lapses **06:00 → 19:00** (summer) over ~35 s with the shade raster sweeping across the districts, the Burj's long shadow reaching across the lake and rotating. A thin arc of the sun path appears (brass hairline). Mark **12:00** and **16:00**; hold on 16:00 where tower shadows have swallowed whole streets. Caption: "A shade map is only true for one minute." |
| 4 | **"A city, built in seconds."** | 90 s | Black ground plane with a hairline grid that fades after use. The **command bar** appears; a typed entry *"Downtown Dubai"* (typewriter, deterministic by `t`). The real **build log** (from `/api/cities/build`, replayed with true counts) scrolls in a slim side ticker while the 3D city assembles in staged waves: ground & roads draw as brass hairlines → footprints rise to heights in a radial ripple from the Burj (staggered by distance) → trees pop in → covered/AC links light up in `oasis`. Final counters (buildings, walkable edges, trees, covered links) animate up from **real `meta.json` values**. **P2:** type *"Abu Dhabi"* and the first city dissolves into the second (morphs/rebuilds); badge says **"Cached build"** or **"Live build"** truthfully; caption "Open data in. Any hot city out." If P2 isn't ready, show the generic pipeline diagram morph instead and the roadmap in Ch. 11. |
| 5 | **"The shade engine."** | 90 s | Camera descends to a mid-height orbit of the Burj/Boulevard. Visualise the method: soft sun rays (thin, warm, low opacity) sweep from the sun direction across towers; shadow raster fades in below. Zoom into one street; edges are coloured by exposure (ramp §12.3) and per-edge value labels appear for two or three edges (real numbers). A small schematic overlay (hairline, serif) shows: *sun position → shadow cast → exposure per street → time-aware routing*. Callout of tests passing (e.g. real count from `pytest` results JSON) and the honest limits tag: "Model v1: buildings · mapped trees · covered links". |
| 6 | **"The route."** (HERO) | 150 s | Command bar: *"Metro to the Opera, 13:30, I'm walking"* (use the actual hero scenario names). The **agent activity feed** slides in (left, refined timeline) streaming the recorded session: `resolve_place`, `get_weather`, `compare_routes`, `optimise_departure`, `verifier: 14/14 claims supported`. Two routes draw: Fastest (slate) vs Coolest (brass). Then the **fly-through**: `FlyRig` follows the Coolest route at eye-to-roof height (low, 2–8 m) with the sun and live HUD (bottom-centre: `sun exposure so far`, `shade %`, `time`, `temperature feel` from weather source), passing through the AC link (grade shifts cool; HUD shows `indoor`); emerging into a tower's shadow. Cut to a **split view**: left Fastest, right Coolest, same clock, HUD stats counting up side by side; final comparison card: *time +X min · sun −Y min · RHL −Z%* (all from `hero.json`). The honest framing line: "Model estimate, not a measurement." |
| 7 | **"Leave later."** | 70 s | A clean chart (visx): x = departure time (5-min steps), y = sun exposure (min), `ember` area with `brass` best-point marker. The sun/shadows scrub in the 3D view behind the chart as the chart's cursor moves; the agent's recommendation line appears ("Leave 15:10 · 4.2 min less sun · 6 min later" values from `departure` output). Show the **why**: the Boulevard east pavement turning to shade (highlighted segments). An **approval** button (Approve plan) is pressed on screen (scripted by `t`), and the plan turns into an "Active plan" card. |
| 8 | **"An agent, not a map."** | 60 s | Show a persona switch (tourist → rider → crew): same engine, different goals. Then the **proactive replan**: simulated clock running; a "20-min delay" event is injected (sim button, labelled "Simulated event"); the Monitor notices, replans, and shows a **diff** (old vs new route/time) and the autonomy policy decision ("Within your L3 limit → auto-applied · Undo"). The Verifier badge is visible. Architecture strip: Planner · Verifier · Monitor · Narrator + tools (hairline diagram, serif labels). |
| 9 | **"Who it's for."** | 60 s | Three cinematic vignettes in the real 3D city, each with a tiny UI mock and **one number from the engine**: **Hotels & tourism boards** — concierge widget from a named hotel (e.g. Address Downtown) → 3 shade-safe walks; **Delivery fleets** — rider cycles the hero rider route; dashboard shows heat-load saved per shift (scenario output); **Outdoor crews** — shift planner timeline with the midday-break policy overlay (labelled "verify"). Then the revenue table (§1.3) fades in, typographically clean; market-size placeholders as `[TEAM TO FILL]` tags. |
| 10 | **"Does it work?"** | 40 s | Evidence chapter, honest and credible: data sources + counts (real), test suite summary (real), the method's limits, and the **field-test plan**: if `data/validation/field_test.json` exists, show measured shaded-vs-sunny surface/air readings (IR thermometer, time, location) as a refined table/chart; else show the plan card ("Field test: Boulevard, 14:00, shaded vs sunny route — result pending") and mark it in `OPEN_ITEMS.md`. |
| 11 | **"Any hot city."** | 40 s | Slow `CraneRig` pull back from Downtown to a **dark globe** (simple sphere, matte) with warm brass points for pre-baked cities (and hollow rings for "next": Doha, Riyadh, Singapore, Phoenix) — only cities that are actually baked are filled; others are hollow and labelled "roadmap". Three-phase roadmap line: *Downtown prototype → UAE cities → global open-data pipeline*. Go-to-market bullets (single line each). |
| 12 | **"The ask."** | 35 s | Return to the Burj at golden hour, sun low, long shadows. Closing line in serif: *"Zill: the agent that routes you through the shade."* Team names (Abhamzay: Mohammed Hamza Ansari · Abhay Preethan) in small caps. A quiet "Try it live" prompt (key `A`). Hold the shot; no cut to black unless the presenter ends. |

### 14.3 Transitions and polish rules
- Chapter changes use **match-cuts or continuous camera moves**, never abrupt wipes. Cross-grade between lighting states over ≥ 1.5 s.
- Typewriter text, counters, chart reveals are driven by chapter-local `t` (deterministic).
- Keep **negative space**. Max 2 text elements on screen besides HUD. Never cover the 3D action centre with UI.
- Grain and vignette constant across chapters for filmic continuity.

---

## 15. The App — `/app` (the real product)

Layout: full-bleed 3D canvas; slim top command bar; left collapsible **Agent panel** (chat + activity feed + autonomy control); right **Journey panel** (Fastest/Balanced/Coolest cards with stats, mode switch walk/cycle/scooter, coolness slider λ, "Leave later?" chart); bottom **Time bar** (date picker with preset chips Winter/Spring/Summer/Hackathon/custom, scrubber from sunrise to sunset with the sun-path arc, play button for time-lapse, "Now" button).
- Click to set A and B on the map (raycast to ground → snap to graph) or type names (gazetteer autocomplete).
- Route compare toggle: Analysis view (exposure-coloured) vs Presentation view (slate/brass).
- "Fly me through it" button: runs `FlyRig` along the selected route with HUD.
- "Try hero journey" chips from `hero.json`.
- Planner view (P1): add stops, drag to reorder, see the day timeline with shade strip per leg and cool-down breaks.
- Persona/wedge routes (P1): `/app?view=fleet`, `/app?view=crew`, and `/embed/hotel` (stand-alone concierge widget with brand-neutral styling).
- Honest-limits footer, OSM attribution, `Model v1` label, source badges (`live`/`cached`/`representative`).

---

## 16. Wedge views (P1)

### 16.1 Hotel concierge (`/embed/hotel?hotel=<name>`)
Starts from the hotel entrance node; shows 3–5 nearby attractions each with the **coolest walk** at a chosen time, time/shade stats, and an "add to my day" action. Light-weight, embed-friendly.

### 16.2 Fleet dashboard (`/app?view=fleet`)
Simulate **N riders (e.g. 12)** running deliveries on scenario routes across a shift using the planner; show aggregate **sun-minutes saved**, RHL saved, extra distance, with per-rider mini-timelines. **All simulated; label "Simulated fleet (scenario)".**

### 16.3 Crew planner (`/app?view=crew`)
Input tasks (site locations, durations), shift window; output: a schedule that places walking legs and tasks into the shadiest windows, flags conflicts with the **UAE_OUTDOOR_WORK** pack (verify), proposes breaks at nearby AC/covered nodes.

---

## 17. Resilience: offline, replay, fallbacks (non-negotiable)

1. **Replay mode:** `backend/replay/` holds recorded sessions `{scenario_id, persona, events[]}` captured by `scripts/record_replay.py` (runs the *real* agent against the *real* tools for the hero scenarios and the replan demo, then stores the SSE events with timestamps). When the API is unreachable or `ZILL_REPLAY=1`, `/api/agent/message` replays the closest matching recording at natural pacing, and the UI shows a small **"Recorded session"** badge (never pretend it's live). Free-text input in replay mode matches against a small intent table and otherwise answers: "This is a recorded session. Connect to the network to chat live."
2. **Weather fallback** as §9. **Fonts, textures, models self-hosted.** No CDN at runtime.
3. **Build artifacts committed** (`data/cities/**`), so `make demo` works on a fresh laptop with just Python + Node, no bake required.
4. **Static fallbacks:** if WebGL fails, `/film` shows chapter stills from `docs/deck_assets/stills/` with arrow-key navigation.
5. **Health page:** `/health` (frontend) shows green/amber for: backend, model reachable, replay available, shade assets loaded, WebGL OK, FPS estimate. The presenter checks this before walking on stage.
6. **Backup video:** `make record` produces `docs/deck_assets/backup_film.mp4` (Playwright video capture of the autoplay Film at 1080p) and `backup_app_demo.mp4`.

---

## 18. Testing and QA

### 18.1 Backend (pytest, must be green)
Geo round-trip; sun goldens; shadow-length geometry tests (§7.3); heightmap rules (parts vs shell, level fallback, Burj ≈ 828 m); graph connectivity per mode; stairs forbidden for cycle/scooter; **routing invariants** (Fastest has the minimum time among all routes; Coolest has the minimum RHL among routes with equal departure; time-dependent lookup uses arrival time; routes never traverse disallowed edges; coolest never has more `sun_exposure_s` than fastest); departure optimiser monotonic sanity; token resolver + fuzz test (§11.4); policy pack checks; API contract tests (schemas); replay playback ordering; city-agnostic bake on a tiny synthetic bbox (mock Overpass fixtures stored in `tests/fixtures/`, no network in CI).

### 18.2 Frontend
TypeScript strict, ESLint clean, `next build` succeeds. Vitest for `geo.ts`, `sun.ts` (vs goldens), master-timeline determinism (`render(t)` twice gives identical camera/sun state), chapter durations sum to 780 s. Playwright smoke: `/film` loads, autoplay advances, chapter jump works, `/app` route request returns and renders stats, replay mode works with the backend's network disabled.

### 18.3 Visual QA loop (mandatory, this is how you "see")
You can read image files. After each frontend phase:
1. Run Playwright (Chromium, `--use-angle=swiftshader` / `--enable-unsafe-swiftshader`, `?q=low&qa=1`) to capture stills at fixed `t` for every chapter (start, mid, end) and key App states into `docs/qa/<phase>/*.png`.
2. **Open each image and critique it** against §12 (palette, bans, composition, legibility, balance, shadows plausibility, nothing clipped, no z-fighting, no overlapped text, the route clearly visible, shade overlay aligned with buildings).
3. Fix, re-capture, re-inspect. **At least two iterations per phase and until you would be proud to show the frame to a design jury.** Record what you changed in `docs/PROGRESS.md`.
4. Alignment check (critical): at 12:00 and 16:00 on `hackathon`, verify the raster shadow edges coincide with the rendered building bases and that shadows point **away** from the visible sun disc. Fix any mirrored axis.

### 18.4 Performance check
Measure p95 frame time on the Film's heaviest chapters (4, 5, 6) in `?debug`; document numbers in `docs/VALIDATION.md`. Fix hotspots (instancing, merged geometry, texture size, post-fx tiers).

---

## 19. Deliverables (all required unless tagged P2/P3)

1. Working monorepo as in §5, `make setup`, `make bake`, `make dev`, `make test`, `make demo`, `make record`.
2. `README.md`, `docs/ARCHITECTURE.md` (with a clean diagram: data → heightmap → shadow → exposure → router → agent → UI; include in the deck), `docs/VALIDATION.md` (data quality counts, test results, limits, perf), `docs/RUNBOOK_DEMO.md` (pre-flight checklist, start commands, what to do if X fails, keyboard shortcuts), `docs/PITCH_STORYBOARD.md` (chapter-by-chapter with timing and what's on screen), **`docs/SPEAKER_NOTES.md`** (2–4 talking points per chapter, written in a natural spoken voice, with the transitions, plus the managerial story: problem → buyer → pricing → GTM → why we win; and likely judge Q&A with honest answers), `docs/OPEN_ITEMS.md` (every placeholder, unverified data, and decision humans must make), `docs/DECISIONS.md`, `docs/PROGRESS.md`.
3. `docs/deck_assets/`: **12–15 high-quality 1920×1080 stills** (named by chapter) + the architecture diagram as PNG/SVG, produced by `make record`/`scripts/export_deck_assets.ts`. The team must email a deck by **Friday 6:00 PM**, so these must be usable in slides as-is.
4. Backup videos (§17.6).

---

## 20. Build order and gates (follow in order; commit and tag at each green gate)

| Phase | Work | Gate (all must be true) |
|---|---|---|
| 0 | Scaffold monorepo, Makefile, env, CI-less test runners, `docs/PROGRESS.md` | `make setup` works; both servers boot with hello-world |
| 1 | Data bake for Downtown Dubai (§6) | `meta.json` counts sane (buildings > 2,000, edges > 10,000); Burj ≈ 828 m; AC link(s) detected or curated; `buildings.glb` loads in a three.js test page |
| 2 | Sun + shadow engine (§7) | all §7 tests green; shade PNGs for 4 preset dates; step ≤ 2.5 s |
| 3 | Exposure + routing + departure + scenarios (§8) | invariants green; `hero.json` written with honest results; route < 300 ms |
| 4 | API (§10) + weather (§9) | contract tests green; `/docs` complete |
| 5 | Agent (§11) incl. verifier, tokens, monitor, replay recorder | recorded sessions exist for 3 hero scenarios + replan demo; fuzz test green; works with **and without** network |
| 6 | 3D scene core (§13) + `/app` basics (§15) | route drawn, shade overlay aligned (18.3 step 4), time slider works at 60 fps; QA images reviewed |
| 7 | **The Film ch. 1–7** (§14) | autoplay plays through chapters 1–7 smoothly; determinism test green; QA images reviewed twice |
| 8 | Film ch. 8–12, wedge views, planner, persona views (P1) | full 13:00 autoplay with no errors; chapter durations sum to 780 s |
| 9 | Resilience (§17), health page, backup recorder, deck assets | works offline; `make record` produces videos + stills |
| 10 | Docs (§19), polish pass, performance pass, final QA | all docs written; OPEN_ITEMS complete; `make test` green; `make demo` from a clean clone works |
| 11 (P2) | Extra cities + Chapter 4 morph + Chapter 11 globe fills | only if Phases 0–10 are green; otherwise skip and note in OPEN_ITEMS |

**Time guidance:** the humans wake up around 07:00 and need a working demo by midday Friday for the 2:00 PM technical mentoring (Dr Afaf Tabach) and 3:00 PM managerial mentoring (Dr Maria Haynes). Prefer a polished P0+P1 over a half-done P2. Leave the last stretch for Phase 10 and the "clean clone" test.

---

## 21. Open items the humans must resolve (copy into `docs/OPEN_ITEMS.md`, extend as you go)
- Verify UAE midday-break rule dates/hours and any current e-scooter lane rules before presenting.
- Verify curated AC links on site (walk the Metro → Dubai Mall link).
- Collect field-test readings (IR thermometer) for Chapter 10 → `data/validation/field_test.json` (schema: `[{ts, place, shaded:bool, surface_c, air_c?, note}]`).
- Fill market-size placeholders with sourced figures; validate pricing hypotheses with mentors.
- Confirm slot length (15 vs 20 min) with organisers; confirm projector resolution/aspect ratio.
- Add the Anthropic API key to `.env`; confirm model IDs.
- Confirm tagline and name.

---

## Appendix A — Environment (`.env.example`)
```
ANTHROPIC_API_KEY=
ZILL_MODEL=claude-sonnet-5-5
ZILL_MODEL_FAST=claude-haiku-5-5
ZILL_REPLAY=0
OVERPASS_URLS=https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter
ZILL_DEFAULT_CITY=dubai_downtown
ZILL_TZ=Asia/Dubai
```

## Appendix B — Key constants (single source of truth: `backend/zill/config.py`, mirrored to the frontend via `/api/config`)
`GRID_RES_M=2.0` · `TIME_STEP_MIN=10` · `MAX_SHADOW_M=1500` · `PED_H=1.5` · speeds `walk 1.4 / cycle 4.5 / scooter 5.0 m/s` · crossing waits `8 s / 10 s` · tree canopy `r=3 m, h=7 m, block=0.65` · indoor `comfort 0.1, crowd 1.15` · λ `0 / 1 / 3` · RHL weights `sun 1.0, shade 0.35, indoor 0.1` · `MAX_TOOL_CALLS=12` · film duration `780 s`.

## Appendix C — "Definition of done" checklist
- [ ] `make demo` on a clean clone opens `/film` and plays 13:00 without error, offline.
- [ ] Hero journey numbers on screen equal `hero.json` and a fresh `/api/route` call.
- [ ] Agent works live **and** in replay; Verifier badge present; no bare computed numbers in agent text.
- [ ] 60 fps (or documented tier fallback) in chapters 4–6.
- [ ] Shadows visibly correct and aligned; no mirrored axes.
- [ ] No neon, no AI-glow, no clutter; QA images reviewed twice.
- [ ] Every placeholder/unverified item listed in `OPEN_ITEMS.md`.
- [ ] Docs, stills, backup videos present.
