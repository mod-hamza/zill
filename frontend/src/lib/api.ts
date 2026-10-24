// Typed API client (CONTRACTS sections 3, 5, 6). All calls go through Next's /api proxy.
import { assetUrl, isFixture } from "./assets";
import { fetchRetrying } from "./busy";

export type Grid = {
  x0: number;
  z0: number;
  rows: number;
  cols: number;
  res_m: number;
};
export type BBox = { s: number; w: number; n: number; e: number };

export type CityMeta = {
  city_id: string;
  name: string;
  timezone: string;
  origin: { lat: number; lon: number };
  bbox_core: BBox;
  bbox_caster?: BBox;
  bbox_scene?: BBox;
  core_grid: Grid;
  caster_grid?: Grid;
  counts: Record<string, number>;
  max_building_height_m?: number;
  attribution?: string;
  dates: Record<string, string>;
  build_log?: { t_ms: number; step: string; count?: number; label?: string }[];
  source?: Record<string, string>;
  synthetic?: boolean;
};

export type GraphJson = {
  nodes: {
    x: number[];
    z: number[];
    lat: number[];
    lon: number[];
    entrance?: boolean[];
    crossing?: boolean[];
  };
  edges: {
    u: number[];
    v: number[];
    length_m: number[];
    highway: string[];
    cls: string[];
    stairs?: boolean[];
    walk: boolean[];
    cycle: boolean[];
    scooter?: boolean[];
    name?: (string | null)[];
    geom: number[][];
  };
};

export type Tree = { x: number; z: number; r: number; h: number; src?: string };
export type Poi = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  x: number;
  z: number;
  node: number;
  kind: string;
  source?: string;
};

export type ShadeStep = {
  hhmm: string;
  ts?: string;
  alt: number;
  az: number;
  night: boolean;
  file: string;
};
export type ShadeIndex = { date: string; date_id: string; steps: ShadeStep[] };

export type Mode = "walk" | "cycle" | "scooter";

export type RouteStats = {
  distance_m: number;
  duration_s: number;
  sun_exposure_s: number;
  shaded_pct: number;
  covered_pct: number;
  indoor_pct: number;
  rhl: number;
  added_time_s: number;
  sun_saved_s: number;
  sun_saved_pct: number;
  rhl_saved_pct: number;
  /** sun mode only: extra direct sun vs fastest */
  sun_gained_s?: number;
  sun_gained_pct?: number;
  note?: string;
};

export type Preference = "shade" | "sun";

export type Segment = {
  edge: number;
  geometry: [number, number][];
  latlon?: [number, number][];
  arrival_s: number;
  t_s: number;
  sun: number;
  cls: string;
};

export type Route = {
  lambda: number;
  label: "fastest" | "balanced" | "coolest" | string;
  mode: Mode;
  depart: string;
  stats: RouteStats;
  nodes: number[];
  edges: number[];
  segments: Segment[];
};

export type Place = {
  name?: string;
  lat: number;
  lon: number;
  node?: number;
  x?: number;
  z?: number;
};

// Well-being block of the route response (CONTRACTS "Overnight additions — Stream A").
export type Wellbeing = {
  preference: Preference;
  uv: {
    index: number | null;
    band: string;
    advice: string;
    basis?: string;
    source?: string;
  } | null;
  heat_stress: {
    apparent_c: number | null;
    band: string;
    advice: string;
    indicative?: boolean;
    source?: string;
    route_rhl?: number;
  } | null;
  daylight_window: {
    active: boolean;
    text: string;
    sun_alt_deg: number;
    shadow_ratio: number | null;
    shadow_text: string;
    uv_index?: number | null;
    cloud_cover_pct?: number | null;
    reasons?: string[];
    rule?: string;
    disclaimer?: string;
  } | null;
  breaks: {
    hot: boolean;
    every_sun_min?: number;
    prompts: { at_s: number; sun_min: number; text: string }[];
    rule?: string;
  } | null;
  overcast: { cloud_cover_pct: number; text: string } | null;
  weather: {
    source: string;
    label: string;
    at?: string;
    apparent_c?: number | null;
    uv_index?: number | null;
    cloud_cover_pct?: number | null;
    shortwave_wm2?: number | null;
  } | null;
  disclaimer?: string;
};

/** `coolest` is the third (lambda 3) route in BOTH modes on the client: in sun mode the API's
 *  `sunniest` is copied into it (normaliseRoute) so the scene and the Film keep one key. */
export type RouteResponse = {
  fastest: Route;
  balanced: Route;
  coolest: Route;
  sunniest?: Route;
  best?: Route;
  preference?: Preference;
  wellbeing?: Wellbeing | null;
  /** Film only: per-route presentation colour overrides (e.g. a shade route drawn brass in the
   *  fastest slot next to a sunniest route); the App never sets it */
  filmColors?: Partial<Record<"fastest" | "balanced" | "coolest", string>>;
  origin: Place;
  dest: Place;
  date_key: string;
};

export function normaliseRoute(
  r: Omit<RouteResponse, "coolest"> & { coolest?: Route },
): RouteResponse {
  const third = r.coolest ?? r.sunniest ?? r.best ?? r.balanced;
  return { ...r, coolest: third, preference: r.preference ?? "shade" };
}

// Places (CONTRACTS "Overnight additions — Stream E").
export type PlaceHit = {
  id: string;
  name: string;
  alt_names?: string[];
  kind: string;
  lat: number;
  lon: number;
  x: number;
  z: number;
  node: number;
  snap_m?: number;
  score?: number;
  source?: "index" | "online" | string;
  matched?: string;
  label?: string;
  curated?: boolean;
};
export type PlaceSearch = {
  city: string;
  q: string;
  results: PlaceHit[];
  online_enabled: boolean;
  timing_ms?: number;
};
export type PlaceParse = {
  origin: PlaceHit | null;
  dest: PlaceHit | null;
  origin_candidates: PlaceHit[];
  dest_candidates: PlaceHit[];
  ambiguous: { origin: boolean; dest: boolean };
  confidence: number;
  parsed: { origin_text?: string; dest_text?: string };
  depart_at?: string;
  depart_time?: string;
  depart_date?: string;
  mode?: Mode;
  preference?: Preference;
  city: string;
};

export type Scenario = {
  id: string;
  persona: string;
  mode: Mode;
  origin: Place & { name: string };
  dest: Place & { name: string };
  date_id: string;
  depart: string;
  fastest: Route;
  balanced: Route;
  coolest: Route;
  /** sun scenarios (hero.json "sun" block) */
  preference?: Preference;
  sunniest?: Route;
  wellbeing?: Wellbeing | null;
};
export type ScenariosJson = {
  generated_at?: string;
  scenarios: Scenario[];
  sun?: { scenarios: Scenario[] };
};

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetchRetrying(url, init);
  if (r.status === 429) throw new Error("The service is busy. Please try again shortly.");
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`);
  return (await r.json()) as T;
}

export const api = {
  meta: (city: string) => getJson<CityMeta>(assetUrl(city, "meta.json")),
  graph: (city: string) => getJson<GraphJson>(assetUrl(city, "graph.json")),
  trees: (city: string) =>
    getJson<{ trees: Tree[] }>(assetUrl(city, "trees.json")),
  pois: (city: string) => getJson<{ pois: Poi[] }>(assetUrl(city, "pois.json")),
  shadeIndex: (city: string, dateId: string) =>
    getJson<ShadeIndex>(assetUrl(city, `shade/${dateId}/index.json`)),
  scenarios: async (city: string): Promise<ScenariosJson | null> => {
    try {
      if (isFixture())
        return await getJson<ScenariosJson>(assetUrl(city, "hero.json"));
      return await getJson<ScenariosJson>(`/api/scenarios/${city}`);
    } catch {
      return null;
    }
  },
  route: async (body: {
    city: string;
    mode: Mode;
    origin: { lat: number; lon: number; node?: number };
    dest: { lat: number; lon: number; node?: number };
    depart_at: string;
    date_key?: string;
    lambdas?: number[];
    preference?: Preference;
  }): Promise<RouteResponse> => {
    if (isFixture()) {
      const { fixtureRoute } = await import("./fixtureRoute");
      return fixtureRoute(body);
    }
    const r = await getJson<RouteResponse>("/api/route", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return normaliseRoute(r);
  },
  searchPlaces: (
    city: string,
    q: string,
    limit = 8,
    init?: RequestInit,
  ): Promise<PlaceSearch> =>
    getJson<PlaceSearch>(
      `/api/places/search?city=${encodeURIComponent(city)}&q=${encodeURIComponent(q)}&limit=${limit}`,
      init,
    ),
  parsePlaces: (city: string, text: string, init?: RequestInit) =>
    getJson<PlaceParse>("/api/places/parse", {
      ...init,
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ city, text }),
    }),
};
