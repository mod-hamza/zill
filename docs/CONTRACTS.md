# CONTRACTS.md — shared interfaces between work streams

Written by the orchestrator before any code. Every sub-agent MUST conform to these
formats so parallel streams integrate without rework. If a contract must change,
change it HERE first (append a dated note at the bottom) and mention it in your report.
`PRD.md` is the product spec; this file pins the details the PRD leaves open.

## 0. Environment & tooling (Windows 11 dev box, must also work on Mac/Linux)
- Python: **3.11** venv at `backend/.venv`, created by `uv venv --python 3.11 backend/.venv`.
  Install: `uv pip install --python backend/.venv -e "backend[dev]"`. Run Python as
  `backend/.venv/Scripts/python` (Windows) — scripts must resolve this cross-platform.
- Node 24 + **npm** (not pnpm/yarn). Frontend in `frontend/`, Next.js 15 App Router, TS strict.
- `make` = GnuWin32 make 3.81 at `C:\Program Files (x86)\GnuWin32\bin\make.exe` (not on PATH by default).
  Therefore **every Makefile recipe is a one-liner `python scripts/zill.py <target>`**; all real
  logic lives in `scripts/zill.py` (stdlib-only, cross-platform, uses `subprocess`). This makes
  `python scripts/zill.py demo` an equivalent fallback when make is absent.
- Ports: FastAPI `:8000`, Next `:3000`. Next `rewrites()` proxies `/api/:path*` → `http://127.0.0.1:8000/api/:path*`.
- Git: **sub-agents never run `git commit`, `git add -A`, `git reset`, `git checkout`, `git stash`.** The
  orchestrator commits. Sub-agents may run `git status`/`git diff` read-only.
- No network at runtime for the Film/App. Network allowed during bake/install.

## 1. LLM provider (overrides PRD §11.1 provider details — user decision 2026-10-22)
- The agent talks to an **OpenAI-compatible Chat Completions endpoint** ("Voke"):
  `ZILL_LLM_BASE_URL=https://www.vokeapi.com/v1`, key in `ZILL_LLM_API_KEY` (fallbacks read in
  order: `ZILL_LLM_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). Use the `openai` Python SDK
  (`OpenAI(base_url=..., api_key=...)`) with tool/function calling (`tools=[{type:"function",...}]`).
- Models: `ZILL_MODEL` (default `claude-sonnet-5-5`), `ZILL_MODEL_FAST` (default `claude-haiku-5-5`).
  Health check calls `GET {base}/models`; if the configured id is absent, fall back through
  `[ZILL_MODEL, claude-sonnet-5-5, claude-opus-5-5, claude-haiku-5-5, first model listed]`
  and report the chosen id in `/api/health`.
- All LLM access goes through ONE module `backend/zill/agent/llm.py` exposing
  `class LLMClient: available() -> bool; chat(messages, tools=None, model=None, temperature=0.2) -> ChatResult`
  so the provider is swappable and tests can inject `FakeLLM`.
- No key / no network / `ZILL_REPLAY=1` → replay mode (PRD §17).

## 2. Coordinate frame & grids
- Local frame per PRD §6.1: `x = (lon−lon0)·111320·cos(lat0)`, `z = −(lat−lat0)·110574`, y up.
  Implemented ONLY in `backend/zill/geo.py` (`to_local(lat, lon, origin) -> (x, z)`,
  `to_wgs84(x, z, origin) -> (lat, lon)`) and mirrored in `frontend/src/lib/geo.ts`.
- **Shade output grid** ("core grid") covers core bbox + 100 m margin. **Caster grid** covers core
  bbox + 900 m. Both cell size `GRID_RES_M = 2.0`, both axis-aligned in the local frame.
- Grid indexing (BOTH grids, Python and TS): array shape `[rows, cols]`, **row 0 = north edge
  (min z), col 0 = west edge (min x)**. Cell `(r, c)` centre: `x = x0 + (c+0.5)·res`,
  `z = z0 + (r+0.5)·res`, where `(x0, z0)` is the grid's NW corner (min x, min z).
- Shade PNG pixels use the SAME orientation: PNG row 0 = north. In three.js the ground plane
  spans `[x0, x0+cols·res] × [z0, z0+rows·res]`; when mapping the texture set `flipY=false`
  and compute UV as `u = (x−x0)/W`, `v = (z−z0)/H` in the shader (do not rely on PlaneGeometry
  default UVs). QA must verify alignment (PRD §18.3.4).

## 3. Baked city artifacts — `data/cities/<city_id>/` (city_id for Dubai: `dubai_downtown`)
### meta.json
```json
{ "city_id":"dubai_downtown", "name":"Downtown Dubai", "timezone":"Asia/Dubai",
  "origin":{"lat":25.1972,"lon":55.2744},
  "bbox_core":{"s":..,"w":..,"n":..,"e":..}, "bbox_caster":{...}, "bbox_scene":{...},
  "core_grid":{"x0":..,"z0":..,"rows":..,"cols":..,"res_m":2.0},
  "caster_grid":{"x0":..,"z0":..,"rows":..,"cols":..,"res_m":2.0},
  "counts":{"buildings":N,"buildings_scene":N,"building_parts":N,"trees":N,"nodes":N,"edges":N,
            "edges_walk":N,"edges_cycle":N,"covered_edges":N,"indoor_edges":N,"ac_link_edges":N,
            "pois":N},
  "height_sources":{"tag":N,"levels":N,"fallback":N,"landmark":N,"part":N},
  "dropped_components":{"walk":N,"cycle":N},
  "max_building_height_m":..,
  "source":{"osm_timestamp":"...","fetched_at":"...","overpass_endpoint":"..."},
  "attribution":"© OpenStreetMap contributors",
  "dates":{"winter":"2026-01-15","spring":"2026-04-15","summer":"2026-07-15","hackathon":"2026-10-24"},
  "build_log":[{"t_ms":0,"step":"geocode","count":..,"label":"..."}, ...] }
```
`build_log` records real step timings/counts from the bake (replayed by `/api/cities/build`).
### buildings.json  (ALL buildings in caster bbox; `in_scene` marks the rendered subset)
```json
{"buildings":[{"id":0,"osm":"way/123","name":"Burj Khalifa"|null,"height":828.0,"min_height":0.0,
  "source":"tag|levels|fallback|landmark|part","kind":"building|part","in_scene":true,
  "footprint":[[x,z],...], "holes":[[[x,z],...]]}]}
```
Coordinates local metres rounded to 0.01; rings not closed (first != last), CCW not guaranteed.
### buildings.glb
One mesh node per 250 m tile (`tile_<i>_<j>`), Y-up local metres, flat roofs, holes handled.
Vertex attributes: POSITION, NORMAL, `_BUILDING_ID` (float), `_HEIGHT` (float). Only `in_scene` buildings.
### trees.json  `{"trees":[{"x":..,"z":..,"r":3.0,"h":7.0,"src":"node|row"}]}`
### graph.json (columnar; undirected edges stored once, router adds both directions)
```json
{"nodes":{"x":[],"z":[],"lat":[],"lon":[],"entrance":[bool],"crossing":[bool]},
 "edges":{"u":[],"v":[],"length_m":[],"highway":[],"cls":["open|covered|indoor|ac_link"],
          "stairs":[bool],"walk":[bool],"cycle":[bool],"scooter":[bool],"name":[str|null],
          "osm":["way/1"],"geom":[[x0,z0,x1,z1,...]]}}
```
Edge index `i` (position in these arrays) is THE edge id used everywhere (exposure rows, segments).
### links.geojson — WGS84 FeatureCollection of covered/indoor/ac_link edges, props `{edge, cls, name, verified}`.
### pois.json — gazetteer resolved from OSM + curated: `{"pois":[{"id":"burj_khalifa","name":"Burj Khalifa","lat":..,"lon":..,"x":..,"z":..,"node":<graph node id>,"kind":"landmark|mall|hotel|metro|park|cafe|water","source":"osm|curated"}]}`
### shade/<date_id>/
- `index.json`: `{"date":"2026-07-15","date_id":"summer","steps":[{"hhmm":"1330","ts":"2026-07-15T13:30:00+04:00","alt":..,"az":..,"night":false,"file":"step_1330.png"}]}`
- `step_HHMM.png`: 8-bit grayscale, core-grid size, 0 = full shade, 255 = full sun; building footprints = 0.
- `exposure_<date_id>.npz` lives at `data/cities/<city_id>/exposure_<date_id>.npz`:
  arrays `exposure` float16 `[n_edges, n_steps]`, `hhmm` int16 `[n_steps]` (e.g. 1330), `minutes` int16 (minutes since midnight).
- `building_mask.png` (core grid, 255 inside buildings) at the city root.

## 4. Python package ownership (who may edit what) — `backend/zill/`
| Path | Owner stream |
|---|---|
| `config.py`, `brand.py`, `geo.py`, `pyproject.toml`, `api/main.py` skeleton | Phase 0 (scaffold). Later streams may APPEND constants to `config.py` in a clearly commented block with their stream name; never edit others' lines. |
| `data/*` | data stream |
| `sun/*`, `shade/*` | shade stream |
| `routing/*`, `services.py` (loads baked city + exposure; `get_city(city_id) -> CityContext`) | routing stream |
| `weather/*`, `api/routes_*.py`, `api/sse.py`, `api/schemas.py` | api stream |
| `agent/*`, `backend/replay/`, `scripts/record_replay.py` | agent stream |
| `frontend/**` | frontend streams (split by directory in their prompts) |

### Public Python interfaces other streams rely on
```python
# zill/sun/position.py
def sun_position(ts: datetime, lat: float, lon: float) -> SunPos  # dataclass alt_deg, az_deg, vector(x,y,z)
def sun_times(date: date, lat, lon, tz) -> dict  # sunrise, sunset, solar_noon (aware datetimes)
# zill/shade/raymarch.py
def compute_sun_fraction(caster: CasterGrid, core: GridSpec, alt_deg, az_deg) -> np.ndarray  # uint8 [rows, cols]
# zill/shade/cache.py
def get_shade_step(city_id, date_id_or_iso, hhmm) -> np.ndarray; def exposure_for(city_id, date_key) -> ExposureTable
# zill/services.py
class CityContext: meta, graph (arrays), buildings, pois, exposure(date_key) -> ExposureTable
def get_city(city_id: str) -> CityContext
# zill/routing/tdsp.py
def route(ctx, origin_node, dest_node, mode, depart: datetime, lam: float, date_key) -> RouteResult
# zill/routing/departure.py
def optimise_departure(ctx, o, d, mode, window_start, window_end, step_min=5, latest_arrival=None, mu=0.25) -> DepartureResult
# zill/routing/scenarios.py  — writes data/scenarios/hero.json
```
`date_key` = preset id (`summer`…) or ISO date. Times are timezone-aware `Asia/Dubai`.

## 5. Route result JSON (API + hero.json + frontend)
```json
{"lambda":3.0,"label":"coolest","mode":"walk","depart":"2026-07-15T13:30:00+04:00",
 "stats":{"distance_m":..,"duration_s":..,"sun_exposure_s":..,"shaded_pct":..,"covered_pct":..,
          "indoor_pct":..,"rhl":..,"added_time_s":..,"sun_saved_s":..,"sun_saved_pct":..,"rhl_saved_pct":..},
 "nodes":[..], "edges":[..],
 "segments":[{"edge":i,"geometry":[[x,z],...],"latlon":[[lat,lon],...],"arrival_s":..,"t_s":..,"sun":0.42,"cls":"open"}]}
```
`POST /api/route` returns `{"fastest":Route,"balanced":Route,"coolest":Route,"origin":Place,"dest":Place,"date_key":"summer"}`.
`*_saved_*` and `added_time_s` are relative to fastest (0 for fastest itself).

## 6. hero.json — `data/scenarios/hero.json`
`{"generated_at":..,"search":{...what was tried...},"scenarios":[{"id":"tourist_walk","persona":"tourist","mode":"walk","origin":{"name","lat","lon","node"},"dest":{...},"date_id":"summer","depart":"13:30","fastest":Route,"coolest":Route,"balanced":Route,"departure":DepartureResult|null}], "candidates":[...top 20 summary rows...]}`
Scenario ids: `tourist_walk` (hero), `rider_cycle`, `crew_shuttle`.

## 7. Agent SSE events (PRD §11.3) — `event: agent` / `data: {"id","ts","type","payload"}`
Recorded sessions: `backend/replay/<scenario_id>.json` = `{"scenario_id","persona","prompt","recorded_at","model","live":true|false,"events":[{"dt_ms":..,"event":{...}}]}`.
`live:false` means generated with the FakeLLM/scripted planner because no key was available —
the UI badge must then say "Scripted session" not "Recorded session".

## 8. Frontend
- `frontend/src/design/tokens.ts` = PRD §12.3 palette exactly; CSS vars in `globals.css`.
- Fonts self-hosted via `next/font/google` (downloaded at build → no runtime network): Fraunces (display) + Inter Tight (UI).
- State: zustand stores in `src/state/`. API client in `src/lib/api.ts` (typed against §5).
- Static baked assets fetched via `/api/cities/{id}/files/{name}` (backend) — frontend never imports from `data/` directly.
- Film timeline: `src/film/master.ts` exports `CHAPTERS: {id, title, dur_s}[]` (sum 780) and
  `evaluate(globalT_s) -> FrameState` (pure). Chapters in `src/film/chapters/chNN.ts` export
  `(t: number /*0..1*/, ctx) -> Partial<FrameState>`.

## Change log
- 2026-10-22 initial (orchestrator).
- 2026-10-22 agent: §7 recording items gain a `phase` field: `{"dt_ms","event","phase":"plan|approve|monitor"}` (message -> approve -> simulate through one recorded session); files also carry `autonomy_level`, `city`, `date_id`, `pacing`, `source`. Replayed events carry `payload.replay = {"source":"recorded|scripted","label","scenario_id","phase"}` for the UI badge. Agent endpoints (all SSE `event: agent`): `POST /api/agent/session {persona,city,date_id,clock,autonomy_level} -> {session_id, mode:"live|replay", badge?}`, `POST /api/agent/message {session_id,text,speed}`, `POST /api/agent/approve {session_id,plan_id?,approve,undo_token?}`, `POST /api/agent/simulate {session_id,type:delay|closure|heat_alert|sun_clock_jump|tick,params}`, `GET /api/agent/replays`, `GET /api/agent/status`. Extra event fields: `approval_request.risk`, `plan_committed.{auto,undo_token,undo}`, `replan.{kind,diff,auto,new_plan_id,routes}`, `message.{template,source}`.

## Overnight additions — Stream E (typed places)
Index file `data/cities/<city>/places.json`: `{"city_id","generated_at","source","attribution","count","dropped_far_from_graph","by_kind","places":[{"id","name","alt_names":[..],"kind","lat","lon","x","z","node","snap_m","osm"}]}`.
Kinds: `station landmark mall square park hotel building street stop amenity food shop other`. Build: `python -m zill.places.build <city_id> [--refresh]` (needs graph.json; uses the cached POI Overpass dump).
Curated `pois.json` entries are merged in (`curated:true`) and keep their ids.

`GET /api/places/search?city=&q=&limit=8&online=true` (q 1..200 chars, limit 1..20) ->
`{"city","q","results":[Place],"online_enabled":bool,"timing_ms"}`; Place = `{"id","name","alt_names","kind","lat","lon","x","z","node","snap_m","score","source":"index|online","matched"?,"label"?,"curated"?}`.
Matching folds case, accents, Arabic letter variants and Norwegian letters (å→a, ø→o, æ→ae); ranks exact > prefix > all-tokens-prefix > fuzzy (capped at 88), weighted by kind. Unknown city -> 404.
`GET /api/places/stats?city=` -> `{"city","count","by_kind"}`.
`POST /api/places/parse {"city","text"}` (text 1..300 chars) ->
`{"origin":Place|null,"dest":Place|null,"origin_candidates":[Place],"dest_candidates":[Place],"ambiguous":{"origin":bool,"dest":bool},"confidence":0..1,"parsed":{"origin_text","dest_text"},"depart_at"?:ISO in city tz,"depart_time"?:"HH:MM","depart_date"?:"YYYY-MM-DD","mode"?:"walk|cycle|scooter","preference"?:"shade|sun","city","timing_ms"}`.
Accepts "from X to Y", "X to Y", "X → Y", "X -> Y", "X - Y", Arabic "من X إلى Y"; "at 15:30", "5pm", "tomorrow 9am", "noon"; "walk/cycle/bike/scooter", "by bike", "shade/shady/sunny/sun". `ambiguous` is true when the best score < 85, or near-tied candidates / same-named branches far apart exist; show a picker from `*_candidates`.
`/api/route`, `/api/departure`, `/api/plan` accept any search-result `id` as a string `origin`/`dest` (or `{"poi": id}`), including `online_*` ids returned by search in the same server process.
Online fallback (Nominatim, `bounded=1` to the city bbox, UA `Zill-hackathon-prototype/0.1`, <= 1 req/s, 2 s timeout, cached, results `source:"online"`) runs only if the best local score < 80; `ZILL_ONLINE_GEOCODE=0` disables it.

## Overnight additions — Stream A (sun mode, well-being, UV and clouds)
`preference: "shade" | "sun"` (default `"shade"`) on `POST /api/route`, `POST /api/departure`, `POST /api/plan`
and on `tdsp.route/compare`, `optimise_departure`, `planner.plan` (Python kwarg `preference=`). Shade mode is
unchanged (hero.json shade scenarios recomputed byte-identical); unknown values → 422.

Sun cost (no negative weights, A* stays admissible): `t + λ·SUN_WEIGHT[mode]·shade_time`, shade_time = `t·(1−sun)` on
open edges and `t` on covered/indoor/ac_link (indoor links get no bonus). λ triple stays [0,1,3].

`POST /api/route` request: `{"city","mode","origin","dest","depart_at","date_key"?,"lambdas"?,"include_segments"?,"preference"?}`.
Response, shade: `{"fastest","balanced","coolest","best"(=coolest),"preference":"shade","origin","dest","date_key","wellbeing","timing_ms"}`.
Response, sun: `{"fastest","balanced","sunniest","best"(=sunniest),"preference":"sun","origin","dest","date_key","wellbeing","timing_ms"}`
(no `coolest` key). Every Route keeps §5; sun-mode stats add `sun_gained_s`, `sun_gained_pct` (vs fastest; 0 for fastest;
`sun_saved_*` stay and are negative). `sunniest` honesty rule: most sun among {λ3, λ1, fastest}; `stats.note` explains a fallback.

`wellbeing` (best route, weather at departure; `null` only if the lookup fails):
```json
{"preference":"sun",
 "uv":{"index":5.0,"band":"low|moderate|high|very high|extreme|unknown","advice":"...","basis":"uv_index_forecast|clear_sky_estimate","source":"WHO Global Solar UV Index bands"},
 "heat_stress":{"apparent_c":24.8,"band":"none|caution|extreme caution|danger|extreme danger|unknown","advice":"...","indicative":true,"source":"...","route_rhl":765.4},
 "daylight_window":{"active":false,"text":"Daylight / vitamin D window. Well-being guidance, not medical advice." | "No daylight / vitamin D window now: <reasons>.",
   "sun_alt_deg":43.7,"shadow_ratio":1.05,"shadow_text":"Your shadow is 1.0× your height.","uv_index":5.0,"cloud_cover_pct":100,"reasons":[...],"rule":"...","disclaimer":"..."},
 "breaks":{"hot":false,"every_sun_min":10.0,"prompts":[{"at_s":900.0,"sun_min":10.0,"text":"..."}],"rule":"..."},
 "overcast":null | {"cloud_cover_pct":100,"text":"Cloud cover is about 100% ... little direct sun today. The sun figures assume a clear sky."},
 "weather":{"source":"cached|live|representative","label":"Recorded weather for 2026-01-15 (Open-Meteo archive)","at":"...","apparent_c":..,"uv_index":..,"cloud_cover_pct":..,"shortwave_wm2":..},
 "disclaimer":"Well-being guidance, not medical advice."}
```
Window rule: altitude ≥ 45° AND rounded UV ≥ 3 AND cloud < 70 % (unknown cloud never opens it). `overcast` is only set in
sun mode. Break prompts only when apparent temperature ≥ 32.2 °C. Route weather uses the recorded file for the date when
one exists (no network wait), else live (10-min cache), else the labelled representative profile.

`POST /api/departure` sun: rows add `shade_s`; `score = shade_s + μ·wait_s`; `recommended` adds `sun_gained_s`,
`sun_gained_pct` (vs the requested departure); response adds top-level `preference` (shade too).
`POST /api/plan` sun: legs are sun-mode balanced routes, ordering/shift scored on shade time; response adds `"preference":"sun"`
(key absent in shade mode). Heat-load cool-down breaks stay on in both modes.

`GET /api/weather` adds `cloud_cover_pct` and `shortwave_wm2` (Open-Meteo hourly `cloud_cover`, `shortwave_radiation`; recorded
files gained them via `python -m zill.weather.record --add-sky`, other values untouched).

`data/scenarios/hero.json` gains key `"sun"` = `{"generated_at","city","search":{procedure S1–S6, attempts, notes, filters,...},
"scenarios":[{"id":"winter_morning_walk"|"office_lunch_walk","persona","preference":"sun","mode","origin","dest","date_id","depart",
"straight_m","fastest","balanced","sunniest","wellbeing","departure"}],"candidates":[top 20 rows]}`. Run: `python -m zill.routing.scenarios --sun`.
The shade search keeps an existing `sun` block when it rewrites the file.

## Overnight additions — Stream C (security layer)

Every `/api/*` request passes `zill.api.security.SecurityMiddleware` before the routes. New responses any client may see:
`429 {"error":{"code":"rate_limited",...}}` with `Retry-After: <s>` (per-IP buckets; agent tier tightest), `413 payload_too_large`
(body > 64 KB), `422 validation_error` (any JSON string > 1,000 chars, agent `text` > 1,000, any query value > 200).
Buckets: agent 8 burst / 10 per min; `/api/shade/compute` and `/api/cities/build` 3 / 2; `/api/route|departure|plan` 30 / 90;
shade tiles and city files 300 / 1,800; other 60 / 240; `/api/health` exempt. `ZILL_RATE_LIMIT=0` disables limiting.
CORS allows only the two production origins and localhost/127.0.0.1/[::1] on any port; methods GET, POST, OPTIONS.
Note for the frontend: handle 429 by honouring `Retry-After`. Other streams: keep new free-text fields short (1,000 chars max).
