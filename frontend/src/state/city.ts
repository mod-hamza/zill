// useCity: baked city assets + loading progress (CONTRACTS section 3).
import { create } from "zustand";
import { useStage } from "./stage";
import { useSun } from "./sun";
import type { Group } from "three";
import {
  api,
  type CityMeta,
  type Poi,
  type ShadeIndex,
  type Tree,
} from "@/lib/api";
import { assetUrl, isFixture } from "@/lib/assets";
import { fetchRetrying } from "@/lib/busy";
import { CityGraph } from "@/lib/graph";

type Part = "meta" | "graph" | "trees" | "pois" | "buildings";
const WEIGHTS: Record<Part, number> = {
  meta: 0.05,
  graph: 0.25,
  trees: 0.05,
  pois: 0.02,
  buildings: 0.63,
};

/** One row of GET /api/cities. */
export type CityListItem = {
  id: string;
  name: string;
  origin?: { lat: number; lon: number } | null;
  bbox?: { s: number; w: number; n: number; e: number } | null;
  counts?: Record<string, number>;
  status: "ready" | "partial" | "incomplete";
  shade_dates?: string[];
  timezone?: string;
  dates?: Record<string, string>;
};

export const DEFAULT_CITY = "dubai_downtown";

/** `?city=` from the URL (client only); null when absent or malformed. */
export function cityFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  const c = new URLSearchParams(window.location.search).get("city");
  return c && /^[a-z0-9_-]{1,40}$/.test(c) ? c : null;
}

type CityState = {
  cityId: string;
  /** GET /api/cities (null until fetched; [] if unavailable, e.g. fixture mode) */
  cities: CityListItem[] | null;
  meta: CityMeta | null;
  graph: CityGraph | null;
  trees: Tree[] | null;
  pois: Poi[] | null;
  buildings: Group | null;
  shadeIndex: Record<string, ShadeIndex>;
  progress: number;
  parts: Partial<Record<Part, number>>;
  error: string | null;
  loaded: boolean;
  fixture: boolean;
  /** Load a city (default: `?city=` or Dubai). Switching cities resets the loaded assets. */
  load: (cityId?: string) => Promise<void>;
  loadCities: () => Promise<CityListItem[]>;
  ensureShadeIndex: (dateId: string) => Promise<ShadeIndex | null>;
};

let inflight: Promise<void> | null = null;
let inflightCity: string | null = null;
let gen = 0;

export const useCity = create<CityState>((set, get) => {
  const setPart = (p: Part, v: number) => {
    const parts = { ...get().parts, [p]: v };
    const progress = (Object.keys(WEIGHTS) as Part[]).reduce(
      (a, k) => a + WEIGHTS[k] * (parts[k] ?? 0),
      0,
    );
    set({ parts, progress });
  };

  return {
    cityId: DEFAULT_CITY,
    cities: null,
    meta: null,
    graph: null,
    trees: null,
    pois: null,
    buildings: null,
    shadeIndex: {},
    progress: 0,
    parts: {},
    error: null,
    loaded: false,
    fixture: false,
    loadCities: async () => {
      const have = get().cities;
      if (have) return have;
      let list: CityListItem[] = [];
      if (!isFixture()) {
        try {
          const r = await fetchRetrying("/api/cities");
          if (r.ok) list = (await r.json()) as CityListItem[];
        } catch {
          list = [];
        }
      }
      set({ cities: list });
      return list;
    },
    load: (cityId) => {
      const target = cityId ?? cityFromUrl() ?? DEFAULT_CITY;
      if (inflight && inflightCity === target) return inflight;
      const my = ++gen;
      const live = () => my === gen;
      inflightCity = target;
      useStage.getState().setShadeReady(false);
      set({
        cityId: target,
        fixture: isFixture(),
        meta: null,
        graph: null,
        trees: null,
        pois: null,
        buildings: null,
        shadeIndex: {},
        progress: 0,
        parts: {},
        error: null,
        loaded: false,
      });
      const p = (async () => {
        try {
          const meta = await api.meta(target);
          if (!live()) return;
          set({ meta });
          useSun.getState().setCity({
            origin: meta.origin,
            tz: meta.timezone || "Asia/Dubai",
            presets: meta.dates,
          });
          setPart("meta", 1);
          const glb = (async () => {
            const { GLTFLoader } =
              await import("three/examples/jsm/loaders/GLTFLoader.js");
            const loader = new GLTFLoader();
            const gltf = await loader.loadAsync(
              assetUrl(target, "buildings.glb"),
              (e) => {
                if (live() && e.total > 0)
                  setPart("buildings", Math.min(0.99, e.loaded / e.total));
              },
            );
            if (!live()) return;
            set({ buildings: gltf.scene });
            setPart("buildings", 1);
          })();
          const graph = api.graph(target).then((g) => {
            if (!live()) return;
            set({ graph: new CityGraph(g) });
            setPart("graph", 1);
          });
          const trees = api
            .trees(target)
            .then((t) => live() && set({ trees: t.trees }))
            .catch(() => live() && set({ trees: [] }))
            .finally(() => live() && setPart("trees", 1));
          const pois = api
            .pois(target)
            .then((x) => live() && set({ pois: x.pois }))
            .catch(() => live() && set({ pois: [] }))
            .finally(() => live() && setPart("pois", 1));
          await Promise.all([glb, graph, trees, pois]);
          if (live()) set({ loaded: true, progress: 1 });
        } catch (e) {
          if (!live()) return;
          set({ error: e instanceof Error ? e.message : String(e) });
          inflight = null;
          inflightCity = null;
        }
      })();
      inflight = p;
      return p;
    },
    ensureShadeIndex: async (dateId) => {
      const have = get().shadeIndex[dateId];
      if (have) return have;
      try {
        const city = get().cityId;
        const idx = await api.shadeIndex(city, dateId);
        if (get().cityId !== city) return null;
        set({ shadeIndex: { ...get().shadeIndex, [dateId]: idx } });
        return idx;
      } catch {
        return null;
      }
    },
  };
});
