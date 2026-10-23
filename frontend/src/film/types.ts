// Film types (PRD 14.1). evaluate(t) -> FrameState is PURE; everything on screen is derived from
// a FrameState plus FilmData (loaded once, real engine output). No timers anywhere.
import type { CityMeta, Route, Scenario } from "@/lib/api";
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
};

// ---------------------------------------------------------------------------------------------
// Overlays (DOM) — each with its own opacity; the Overlay component draws them.
export type OverlayItem =
  | { kind: "title"; text: string; sub?: string; opacity: number; size?: "hero" | "card"; subOpacity?: number }
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
  | { kind: "globelabels"; opacity: number };

export type HudState = {
  sunS: number;
  shadePct: number;
  clock: string;
  feel?: number | null;
  feelBadge?: string;
  cls?: string;
  color?: string;
};

export type FrameState = {
  t: number;
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
  /** seconds of continuous camera/sun blend from the previous chapter's end (0 = cut) */
  blendIn?: number;
  /** a soft ink dip across the boundary into this chapter (seconds, total) */
  dipIn?: number;
};
