// Film types (PRD 14.1). evaluate(t) -> FrameState is PURE; everything on screen is derived from
// a FrameState plus FilmData (loaded once, real engine output). No timers anywhere.
import type { CityMeta, Route, RouteResponse, Scenario } from "@/lib/api";
import type { RoutePolyline } from "@/lib/routeGeom";
import type { RigState, V3 } from "@/three/rigs";
import type { AgentEvent } from "@/app-ui/feed";

export type RouteKey = "fastest" | "balanced" | "coolest";

export type ReplayItem = { dt_ms: number; phase?: string; event: AgentEvent };
export type Replay = {
  scenario_id: string;
  persona?: string;
  prompt?: string;
  recorded_at?: string;
  model?: string;
  live?: boolean;
  events: ReplayItem[];
};

export type Weather = {
  source?: string;
  label?: string;
  temperature_c?: number;
  apparent_c?: number;
  humidity_pct?: number;
  uv_index?: number;
  heat_alert?: boolean;
};

export type TestResults = {
  backend?: { passed: number; failed: number };
  frontend?: { passed: number; failed: number };
  ts?: string;
};

export type BuildLogRow = {
  t_ms: number;
  dur_ms?: number;
  duration_ms?: number;
  step: string;
  count?: number;
  label?: string;
};

export type DepartureRow = {
  depart: string;
  depart_time: string;
  duration_s: number;
  sun_exposure_s: number;
  shaded_pct?: number;
  rhl?: number;
  wait_s?: number;
  arrive_time?: string;
  feasible?: boolean;
  score?: number;
  recommended?: boolean;
};

export type Departure = {
  table: DepartureRow[];
  recommended?: DepartureRow & { sun_saved_s?: number; wait_min?: number };
  requested?: DepartureRow;
  why?: {
    changes?: { edge?: number; [k: string]: unknown }[];
    shift_min?: number;
    route_changed?: boolean;
    from_depart?: string;
    to_depart?: string;
  };
};

export type HeroScenario = Scenario & { departure?: Departure | null };

/** Business facts extracted verbatim from docs/COSTS.md, SECURITY.md, ACCURACY.md by
 *  scripts/sync-film-data.mjs (public/film-data/facts.json). null = not found -> the row is not shown. */
export type LoadRow = {
  users: number | null;
  requests: number | null;
  rps: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  errors: number | null;
};
export type Facts = {
  costs: {
    source: string;
    vps_price: string | null;
    go_usd_month: number | null;
    goplus_usd_month: number | null;
    llm: { model: string; go_requests_month: number | null; go_conversations_month: number | null }[];
    requests_per_conversation: number | null;
    local_load: LoadRow[];
    live_load: LoadRow[];
    shade_bake_s: number | null;
    shade_bake_dates: string | null;
    data_bake_s: number | null;
  };
  security: { source: string; tests: number | null; body_cap_kb: number | null };
  accuracy: {
    source: string;
    shadow_step_min: number | null;
    grid_m: number | null;
    departure_step_min: number | null;
    weather_hourly: boolean;
    sun_within_deg: number | null;
    heights_fallback_pct: number | null;
    weekly_rebake: string | null;
    field_validation: string | null;
  };
};

/** "Two directions" (Ch.8): one trip, the same minute, shade mode vs sun mode. The sun side is a
 *  hero.json `sun` scenario verbatim; the shade side is /api/route (preference shade) for the same
 *  origin, destination and departure, computed at load. */
export type Directions = {
  scenario: HeroScenario;
  /** shade-mode best route for the same trip (null if the API was unreachable) */
  shade: Route | null;
  /** how the scenario was chosen (documented rule) */
  rule: string;
};

/** A route set the Film can put on the shared Routes layer by key (FrameState.routes.result). */
export type RouteSet = RouteResponse & { city: string };

export type AcLinkStory = {
  origin?: string;
  dest?: string;
  date_id?: string;
  depart?: string;
  uses_ac_link?: boolean;
  fastest_with_links?: {
    distance_m: number;
    duration_s: number;
    sun_exposure_s: number;
    indoor_pct: number;
  };
  note?: string;
};

export type HotelWalk = {
  dest: string;
  route: Route;
};

/** A precomputed per-route bundle (polylines + authored fly path). */
export type RouteGeo = {
  route: Route;
  poly: RoutePolyline;
  /** fly path at street level with heights authored over buildings */
  fly: V3[];
  /** cumulative sun (s) at each segment end, for counters that end exactly on stats */
  bbox: { x0: number; x1: number; z0: number; z1: number; cx: number; cz: number; ext: number };
};

/** One leg/route summary of a case study, verbatim from case_studies.json. */
export type CaseRouteStats = {
  duration_s?: number;
  duration_min?: number;
  direct_sun_s?: number;
  direct_sun_min?: number;
  distance_m?: number;
};
/** data/scenarios/case_studies.json `cases[]` (zill.routing.case_studies; only the fields the Film reads) */
export type CaseStudyJson = {
  id: string;
  label?: string;
  persona?: string;
  city: string;
  date?: string;
  date_id: string;
  depart: string;
  depart_iso?: string;
  origin: { name: string; lat: number; lon: number; node?: number };
  dest: { name: string; lat: number; lon: number; node?: number };
  turnaround?: string;
  mode: "walk" | "cycle" | "scooter" | "run";
  pace?: { speed_m_s?: number; min_per_km?: number };
  preference: "shade" | "sun";
  route_shape?: string;
  fastest?: CaseRouteStats;
  best?: CaseRouteStats;
  delta?: {
    added_time_min?: number;
    sun_saved_min?: number;
    sun_saved_pct?: number;
    sun_gained_min?: number;
    sun_gained_pct?: number;
  };
  wellbeing?: { uv_index?: number | null; uv_band?: string; sun_altitude_deg?: number };
  per_shift?: { assumption?: string; trips?: number; is_assumption?: boolean; sun_saved_min?: number };
};
/** a case study + the key of its route set (drawn from /api/route at load; null if unreachable) */
export type CaseStudy = { c: CaseStudyJson; routeKey: string | null };

export type FilmData = {
  meta: CityMeta;
  hero: HeroScenario;
  scenarios: HeroScenario[];
  heroGeo: { fastest: RouteGeo; coolest: RouteGeo };
  scenarioGeo: Record<string, { fastest: RouteGeo; coolest: RouteGeo }>;
  /** three exposure-labelled segments for Ch.5 (indices into hero.coolest.segments) */
  labelSegs: number[];
  /** ch5 street focus point and its route window */
  streetFocus: { x: number; z: number; bearing: number };
  replays: Record<string, Replay>;
  weather: Weather | null;
  tests: TestResults | null;
  shadeBakeLog: BuildLogRow[];
  acLink: AcLinkStory | null;
  /** centre + extent of the graph's ac_link edges (from graph.json) */
  acLinkArea: { x: number; z: number; ext: number } | null;
  hotelWalks: HotelWalk[];
  hotelName: string | null;
  notes: Record<string, string[]>;
  hasFieldTest: boolean;
  policy: { label?: string; verified?: boolean; midday_window?: { start: string; end: string; from_month_day?: string; to_month_day?: string } } | null;
  bakedCities: { id: string; name: string; lat: number; lon: number }[];
  /** Burj Khalifa top height from meta (m) */
  burjH: number;
  /** Ch.8 shade-vs-sun pair (null if hero.json has no sun scenarios) */
  directions: Directions | null;
  /** Ch.9: Oslo meta + the hero_oslo.json `sun` winter scenario (null if Oslo is not baked) */
  oslo: { meta: CityMeta; scenario: HeroScenario } | null;
  /** extra route sets by key ("dir_shade", "dir_sun", "dir_both", "oslo_sun") */
  routeSets: Record<string, RouteSet>;
  /** preset dates per city id (for the sun clock when the Film switches city) */
  cityDates: Record<string, Record<string, string>>;
  facts: Facts | null;
  /** short cut "Case studies" (public/film-data/case_studies.json), Dubai cases first */
  cases: CaseStudy[];
};

// ---------------------------------------------------------------------------------------------
// Overlays (DOM) — each with its own opacity; the Overlay component draws them.
export type OverlayItem =
  | { kind: "title"; text: string; sub?: string; ar?: string; opacity: number; size?: "hero" | "card"; subOpacity?: number }
  | { kind: "caption"; text: string; opacity: number; align?: "left" | "center" }
  | { kind: "command"; text: string; caret: boolean; opacity: number; label?: string }
  | { kind: "buildlog"; rows: { label: string; step: string; count?: number; ms?: number }[]; opacity: number; badge: string }
  | { kind: "counters"; items: { label: string; value: number; final: number }[]; opacity: number }
  | { kind: "pipeline"; progress: number; opacity: number; line: string }
  | { kind: "schematic"; progress: number; opacity: number }
  | { kind: "evidence"; opacity: number; tests: TestResults | null; limits: string }
  | { kind: "aclink"; opacity: number; story: AcLinkStory }
  | { kind: "feed"; replayId: string; cursorMs: number; opacity: number; phases?: string[]; title?: string }
  | { kind: "hud"; opacity: number; hud: HudState; position?: "center" | "left" | "right"; label?: string }
  | { kind: "compare"; opacity: number }
  | { kind: "honest"; text: string; opacity: number }
  | { kind: "chart"; opacity: number; cursor: number; reveal: number; approve: number; active: number; rec: number }
  | { kind: "personas"; opacity: number; active: number; progress: number }
  | { kind: "replan"; opacity: number; progress: number }
  | { kind: "architecture"; opacity: number; progress: number }
  | { kind: "vignette"; which: "hotel" | "fleet" | "crew"; opacity: number; progress: number }
  | { kind: "revenue"; opacity: number; progress: number }
  | { kind: "fieldtest"; opacity: number }
  | { kind: "roadmap"; opacity: number; progress: number }
  | { kind: "closing"; opacity: number; teamOpacity: number; tryOpacity: number }
  | { kind: "splitline"; opacity: number; left: string; right: string }
  | { kind: "edgelabels"; opacity: number; segs: number[] }
  | { kind: "arclabels"; opacity: number; marks: { hhmm: string; opacity: number }[] }
  | { kind: "globelabels"; opacity: number }
  | { kind: "directions"; opacity: number; phase: "shade" | "sun" | "both"; progress: number }
  | { kind: "wellbeing"; opacity: number; which: "directions" | "oslo" }
  | { kind: "oslo"; opacity: number; progress: number }
  | { kind: "privacy"; opacity: number; progress: number }
  | { kind: "costs"; opacity: number; progress: number }
  | { kind: "accuracy"; opacity: number; progress: number }
  | { kind: "pricing"; opacity: number }
  | { kind: "casestudy"; opacity: number; index: number; progress: number };

export type HudState = {
  sunS: number;
  shadePct: number;
  clock: string;
  feel?: number | null;
  feelBadge?: string;
  cls?: string;
  color?: string;
};

/** the Film's home city (every chapter except "Winter in Oslo") */
export const FILM_HOME_CITY = "dubai_downtown";

export type FrameState = {
  t: number;
  /** city id whose 3D scene this frame shows (the Film switches the shared scene by id) */
  city: string;
  chapter: number;
  localT: number;
  localS: number;
  camera: RigState;
  sun: { dateKey: string; minutes: number };
  /** Film look strength (0..1) */
  look: number;
  /** ink dip (DOM), 0..1 */
  fade: number;
  indoor: number;
  blackout: number;
  skyDim: number;
  fogScale: number;
  shadows: boolean;
  build: { grid: number; roads: number; revealR: number; treeR: number; links: number; linkHighlight: number; linkPx: number };
  /** fraction of lit window floors at dawn/dusk (null = scene default) */
  litFrac: number | null;
  routes: {
    result: "hero" | string | null;
    view: "presentation" | "analysis";
    selected: RouteKey;
    reveal: { fastest: number; coolest: number };
    opacity: number;
  };
  /** route line width multiplier (aerial shots) */
  routeWidth: number;
  travellers: { key: RouteKey; scenario: string; at: number; color: string }[];
  split: { amount: number; camera: RigState } | null;
  shimmer: number;
  sunArc: number;
  sunRays: number;
  globe: number;
  overlays: OverlayItem[];
};

export type ChapterOut = Partial<Omit<FrameState, "build">> & { build?: Partial<FrameState["build"]> };
export type ChapterFn = (t: number, data: FilmData) => ChapterOut;

export type ChapterDef = {
  id: string;
  title: string;
  dur_s: number;
  fn: ChapterFn;
  /** docs/SPEAKER_NOTES.md chapter number of this chapter's notes (written before the renumbering) */
  notes?: number;
  /** presenter cue when the chapter has no SPEAKER_NOTES section (or to replace it in the short cut) */
  cue?: string;
  /** seconds of continuous camera/sun blend from the previous chapter's end (0 = cut) */
  blendIn?: number;
  /** a soft ink dip across the boundary into this chapter (seconds, total) */
  dipIn?: number;
};
