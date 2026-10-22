// useRoute: A/B endpoints, travel mode, coolness lambda, API results and the view mode.
import { create } from "zustand";
import {
  api,
  type Mode,
  type Route,
  type RouteResponse,
  type Scenario,
} from "@/lib/api";
import { useCity } from "./city";
import { useSun } from "./sun";
import { minutesToHHMM, TZ_OFFSET } from "@/lib/sun";

export type Endpoint = {
  node: number;
  x: number;
  z: number;
  lat: number;
  lon: number;
  name?: string;
};
export type RouteKey = "fastest" | "balanced" | "coolest";
export type RouteView = "analysis" | "presentation";

type RouteState = {
  a: Endpoint | null;
  b: Endpoint | null;
  mode: Mode;
  lambda: number;
  result: RouteResponse | null;
  selected: RouteKey;
  view: RouteView;
  loading: boolean;
  error: string | null;
  scenarios: Scenario[];
  activeScenario: string | null;
  /** fly-through playback 0..1 (null when not flying) */
  flyT: number | null;
  setEndpoint: (which: "a" | "b", e: Endpoint | null) => void;
  clickPoint: (e: Endpoint) => void;
  setMode: (m: Mode) => void;
  setLambda: (l: number) => void;
  setSelected: (k: RouteKey) => void;
  setView: (v: RouteView) => void;
  setFlyT: (t: number | null) => void;
  request: () => Promise<void>;
  loadScenarios: () => Promise<void>;
  applyScenario: (id: string) => void;
  clear: () => void;
};

let reqSeq = 0;

export const useRoute = create<RouteState>((set, get) => ({
  a: null,
  b: null,
  mode: "walk",
  lambda: 1,
  result: null,
  selected: "coolest",
  view: "presentation",
  loading: false,
  error: null,
  scenarios: [],
  activeScenario: null,
  flyT: null,
  setEndpoint: (which, e) =>
    set({ [which]: e, activeScenario: null } as Partial<RouteState>),
  clickPoint: (e) => {
    const { a, b } = get();
    if (!a || (a && b)) {
      set({
        a: e,
        b: null,
        result: null,
        error: null,
        activeScenario: null,
        flyT: null,
      });
    } else {
      set({ b: e, activeScenario: null });
      void get().request();
    }
  },
  setMode: (mode) => {
    set({ mode });
    if (get().a && get().b) void get().request();
  },
  setLambda: (lambda) => set({ lambda }),
  setSelected: (selected) => set({ selected }),
  setView: (view) => set({ view }),
  setFlyT: (flyT) => set({ flyT }),
  request: async () => {
    const { a, b, mode, lambda } = get();
    if (!a || !b) return;
    const city = useCity.getState().cityId;
    const { dateIso, dateKey, minutes } = useSun.getState();
    const seq = ++reqSeq;
    set({ loading: true, error: null });
    try {
      const res = await api.route({
        city,
        mode,
        origin: { lat: a.lat, lon: a.lon, node: a.node },
        dest: { lat: b.lat, lon: b.lon, node: b.node },
        depart_at: `${dateIso}T${minutesToHHMM(minutes, ":")}:00${TZ_OFFSET}`,
        date_key: dateKey,
        lambdas: [0, lambda, 3],
      });
      if (seq !== reqSeq) return;
      set({ result: res, loading: false });
    } catch (e) {
      if (seq !== reqSeq) return;
      set({
        loading: false,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  },
  loadScenarios: async () => {
    const j = await api.scenarios(useCity.getState().cityId);
    set({ scenarios: j?.scenarios ?? [] });
  },
  applyScenario: (id) => {
    const s = get().scenarios.find((x) => x.id === id);
    if (!s) return;
    const g = useCity.getState().graph;
    const mk = (p: Scenario["origin"]): Endpoint => {
      const node = p.node ?? (g ? g.nearest(p.x ?? 0, p.z ?? 0) : -1);
      return {
        node,
        x: p.x ?? (g && node >= 0 ? g.x[node]! : 0),
        z: p.z ?? (g && node >= 0 ? g.z[node]! : 0),
        lat: p.lat,
        lon: p.lon,
        name: p.name,
      };
    };
    const sun = useSun.getState();
    sun.setDate(s.date_id);
    const [hh, mm] = s.depart.split(":").map(Number);
    sun.setMinutes((hh ?? 13) * 60 + (mm ?? 0));
    set({
      a: mk(s.origin),
      b: mk(s.dest),
      mode: s.mode,
      result: {
        fastest: s.fastest,
        balanced: s.balanced,
        coolest: s.coolest,
        origin: s.origin,
        dest: s.dest,
        date_key: s.date_id,
      },
      activeScenario: id,
      selected: "coolest",
      error: null,
      flyT: null,
    });
  },
  clear: () =>
    set({
      a: null,
      b: null,
      result: null,
      error: null,
      activeScenario: null,
      flyT: null,
    }),
}));

export function routeOf(res: RouteResponse | null, k: RouteKey): Route | null {
  return res ? res[k] : null;
}
