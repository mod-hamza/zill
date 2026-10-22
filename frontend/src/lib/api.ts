// Typed API client (CONTRACTS sections 3, 5, 6). All calls go through Next's /api proxy.
import { assetUrl, isFixture } from "./assets";

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
  note?: string;
};

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

export type RouteResponse = {
  fastest: Route;
  balanced: Route;
  coolest: Route;
  origin: Place;
  dest: Place;
  date_key: string;
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
};
export type ScenariosJson = { generated_at?: string; scenarios: Scenario[] };

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
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
  }): Promise<RouteResponse> => {
    if (isFixture()) {
      const { fixtureRoute } = await import("./fixtureRoute");
      return fixtureRoute(body);
    }
    return getJson<RouteResponse>("/api/route", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  },
};
