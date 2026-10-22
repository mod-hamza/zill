// useCity: baked city assets + loading progress (CONTRACTS section 3).
import { create } from "zustand";
import type { Group } from "three";
import {
  api,
  type CityMeta,
  type Poi,
  type ShadeIndex,
  type Tree,
} from "@/lib/api";
import { assetUrl, isFixture } from "@/lib/assets";
import { CityGraph } from "@/lib/graph";

type Part = "meta" | "graph" | "trees" | "pois" | "buildings";
const WEIGHTS: Record<Part, number> = {
  meta: 0.05,
  graph: 0.25,
  trees: 0.05,
  pois: 0.02,
  buildings: 0.63,
};

type CityState = {
  cityId: string;
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
  load: (cityId?: string) => Promise<void>;
  ensureShadeIndex: (dateId: string) => Promise<ShadeIndex | null>;
};

let inflight: Promise<void> | null = null;

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
    cityId: "dubai_downtown",
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
    load: (cityId = "dubai_downtown") => {
      if (inflight) return inflight;
      set({ cityId, fixture: isFixture() });
      inflight = (async () => {
        try {
          const meta = await api.meta(cityId);
          set({ meta });
          setPart("meta", 1);
          const glb = (async () => {
            const { GLTFLoader } =
              await import("three/examples/jsm/loaders/GLTFLoader.js");
            const loader = new GLTFLoader();
            const gltf = await loader.loadAsync(
              assetUrl(cityId, "buildings.glb"),
              (e) => {
                if (e.total > 0)
                  setPart("buildings", Math.min(0.99, e.loaded / e.total));
              },
            );
            set({ buildings: gltf.scene });
            setPart("buildings", 1);
          })();
          const graph = api.graph(cityId).then((g) => {
            set({ graph: new CityGraph(g) });
            setPart("graph", 1);
          });
          const trees = api
            .trees(cityId)
            .then((t) => set({ trees: t.trees }))
            .catch(() => set({ trees: [] }))
            .finally(() => setPart("trees", 1));
          const pois = api
            .pois(cityId)
            .then((p) => set({ pois: p.pois }))
            .catch(() => set({ pois: [] }))
            .finally(() => setPart("pois", 1));
          await Promise.all([glb, graph, trees, pois]);
          set({ loaded: true, progress: 1 });
        } catch (e) {
          set({ error: e instanceof Error ? e.message : String(e) });
          inflight = null;
        }
      })();
      return inflight;
    },
    ensureShadeIndex: async (dateId) => {
      const have = get().shadeIndex[dateId];
      if (have) return have;
      try {
        const idx = await api.shadeIndex(get().cityId, dateId);
        set({ shadeIndex: { ...get().shadeIndex, [dateId]: idx } });
        return idx;
      } catch {
        return null;
      }
    },
  };
});
