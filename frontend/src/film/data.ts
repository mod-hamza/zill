// FilmData loader (PRD 14.1): fetched ONCE behind the loading screen. Every number the Film shows
// comes from these payloads (API = real engine output; /film-data/* = verbatim copies of
// backend/replay/*.json, data/test_results.json, docs/SPEAKER_NOTES.md made by
// scripts/sync-film-data.mjs because the API has no endpoint for replay bodies).
import { create } from "zustand";
import type { Object3D } from "three";
import { api, type Route, type ScenariosJson } from "@/lib/api";
import { assetUrl } from "@/lib/assets";
import { routePolyline } from "@/lib/routeGeom";
import { useCity } from "@/state/city";
import { authorFlyPath } from "@/three/AppDrivers";
import type { V3 } from "@/three/rigs";
import type {
  AcLinkStory,
  BuildLogRow,
  FilmData,
  HeroScenario,
  HotelWalk,
  Replay,
  RouteGeo,
  TestResults,
  Weather,
} from "./types";

export const HERO_ID = "tourist_walk";
/** street-level fly heights for the Film (PRD 14.2 Ch.6: 2–8 m) */
export const FILM_EYE_M = 4.2;

async function j<T>(url: string, init?: RequestInit): Promise<T | null> {
  try {
    const r = await fetch(url, init);
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export function routeGeo(route: Route, buildings: Object3D | null): RouteGeo {
  const poly = routePolyline(route);
  const fly = authorFlyPath(poly, buildings).map(
    ([x, y, z]) => [x, Math.max(FILM_EYE_M, y), z] as V3,
  );
  let x0 = Infinity,
    x1 = -Infinity,
    z0 = Infinity,
    z1 = -Infinity;
  for (let i = 0; i < poly.pts.length; i += 2) {
    x0 = Math.min(x0, poly.pts[i]!);
    x1 = Math.max(x1, poly.pts[i]!);
    z0 = Math.min(z0, poly.pts[i + 1]!);
    z1 = Math.max(z1, poly.pts[i + 1]!);
  }
  return {
    route,
    poly,
    fly,
    bbox: {
      x0,
      x1,
      z0,
      z1,
      cx: (x0 + x1) / 2,
      cz: (z0 + z1) / 2,
      ext: Math.max(x1 - x0, z1 - z0, 200),
    },
  };
}

const segLen = (g: [number, number][]) => {
  let L = 0;
  for (let k = 1; k < g.length; k++)
    L += Math.hypot(g[k]![0] - g[k - 1]![0], g[k]![1] - g[k - 1]![1]);
  return L;
};
const segMid = (g: [number, number][]): [number, number] => {
  const L = segLen(g);
  let acc = 0;
  for (let k = 1; k < g.length; k++) {
    const d = Math.hypot(g[k]![0] - g[k - 1]![0], g[k]![1] - g[k - 1]![1]);
    if (acc + d >= L / 2) {
      const u = (L / 2 - acc) / Math.max(d, 1e-6);
      return [
        g[k - 1]![0] + (g[k]![0] - g[k - 1]![0]) * u,
        g[k - 1]![1] + (g[k]![1] - g[k - 1]![1]) * u,
      ];
    }
    acc += d;
  }
  return g[0]!;
};
export { segMid, segLen };

/**
 * Ch.5 street: the ~320 m window of the coolest route with the widest spread of per-edge sun
 * values; label its sunniest, shadiest and one middle edge (each >= 14 m long). Deterministic.
 */
export function pickStreet(route: Route): {
  labelSegs: number[];
  focus: { x: number; z: number; bearing: number };
} {
  const segs = route.segments;
  const mids = segs.map((s) => segMid(s.geometry));
  const lens = segs.map((s) => segLen(s.geometry));
  let best = { score: -1, idx: [] as number[] };
  for (let i = 0; i < segs.length; i++) {
    const near: number[] = [];
    for (let k = 0; k < segs.length; k++) {
      if (lens[k]! < 14) continue;
      const d = Math.hypot(mids[k]![0] - mids[i]![0], mids[k]![1] - mids[i]![1]);
      if (d <= 160) near.push(k);
    }
    if (near.length < 3) continue;
    const vals = near.map((k) => segs[k]!.sun);
    const spread = Math.max(...vals) - Math.min(...vals);
    if (spread > best.score + 1e-9) best = { score: spread, idx: near };
  }
  if (best.idx.length < 3) {
    const order = segs.map((_, k) => k).sort((a, b) => lens[b]! - lens[a]!);
    best.idx = order.slice(0, 3);
  }
  const byVal = [...best.idx].sort((a, b) => segs[a]!.sun - segs[b]!.sun);
  const lo = byVal[0]!;
  const hi = byVal[byVal.length - 1]!;
  const midTarget = (segs[lo]!.sun + segs[hi]!.sun) / 2;
  const mid = byVal
    .slice(1, -1)
    .sort(
      (a, b) =>
        Math.abs(segs[a]!.sun - midTarget) - Math.abs(segs[b]!.sun - midTarget),
    )[0];
  const labelSegs = [hi, ...(mid !== undefined ? [mid] : []), lo].sort((a, b) => a - b);
  const cx = labelSegs.reduce((a, k) => a + mids[k]![0], 0) / labelSegs.length;
  const cz = labelSegs.reduce((a, k) => a + mids[k]![1], 0) / labelSegs.length;
  // look along the route's local direction, from its side
  const a = mids[labelSegs[0]!]!;
  const b = mids[labelSegs[labelSegs.length - 1]!]!;
  const dir = (Math.atan2(b[0] - a[0], -(b[1] - a[1])) * 180) / Math.PI;
  return { labelSegs, focus: { x: cx, z: cz, bearing: dir + 125 } };
}

type DataStore = {
  data: FilmData | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  progress: number;
  load: () => Promise<void>;
};

let inflight: Promise<void> | null = null;

export const useFilmData = create<DataStore>((set, get) => ({
  data: null,
  status: "idle",
  error: null,
  progress: 0,
  load: () => {
    if (inflight) return inflight;
    set({ status: "loading" });
    inflight = (async () => {
      try {
        await useCity.getState().load();
        const city = useCity.getState();
        if (!city.meta || !city.loaded) throw new Error(city.error ?? "city did not load");
        const cityId = city.cityId;
        const meta = city.meta;
        set({ progress: 0.2 });
        const sc = (await api.scenarios(cityId)) as
          | (ScenariosJson & { ac_link_story?: AcLinkStory })
          | null;
        const scenarios = (sc?.scenarios ?? []) as HeroScenario[];
        const hero = scenarios.find((s) => s.id === HERO_ID) ?? scenarios[0];
        if (!hero) throw new Error("no hero scenario in /api/scenarios");
        const dateIso = meta.dates[hero.date_id] ?? hero.date_id;
        const departIso = `${dateIso}T${hero.depart}:00+04:00`;

        const manifest = (await j<{ files: string[] }>("/film-data/manifest.json"))?.files ?? [];
        const replayIds = ["tourist_walk", "replan_demo", "rider_cycle", "crew_shuttle"].filter((id) =>
          manifest.includes(`replays/${id}.json`),
        );
        const policy = manifest.includes("policy_uae_outdoor_work.json")
          ? await j<FilmData["policy"]>("/film-data/policy_uae_outdoor_work.json")
          : null;
        const [replayList, weather, tests, bake, notes, field, cities] = await Promise.all([
          Promise.all(
            replayIds.map((id) => j<Replay>(`/film-data/replays/${id}.json`)),
          ),
          j<Weather>(
            `/api/weather?city=${encodeURIComponent(cityId)}&at=${encodeURIComponent(departIso)}`,
          ),
          j<TestResults>("/film-data/test_results.json"),
          j<{ build_log?: BuildLogRow[] }>(assetUrl(cityId, "shade/bake_log.json")),
          j<Record<string, string[]>>("/film-data/notes.json"),
          manifest.includes("field_test.json") ? j<unknown>("/film-data/field_test.json") : Promise.resolve(null),
          j<{ id: string; name: string; status?: string; origin?: { lat: number; lon: number } }[]>(
            "/api/cities",
          ),
        ]);
        const replays: Record<string, Replay> = {};
        replayIds.forEach((id, i) => {
          const r = replayList[i];
          if (r?.events?.length) replays[id] = r;
        });
        set({ progress: 0.5 });

        // Hotel concierge vignette (Ch.9): three coolest walks from a named hotel, computed live
        // by /api/route at the hero date/time (engine output, not hard-coded).
        const pois = city.pois ?? [];
        const hotel =
          pois.find((p) => p.id === "address_downtown") ?? pois.find((p) => p.kind === "hotel");
        const hotelWalks: HotelWalk[] = [];
        if (hotel) {
          // gazetteer places first (pois.json lists the curated gazetteer hits before other OSM POIs)
          const dests = pois
            .slice(0, 20)
            .filter((p) => ["landmark", "park", "mall", "water"].includes(p.kind) && p.id !== hotel.id)
            .map((p) => ({ p, d: Math.hypot(p.x - hotel.x, p.z - hotel.z) }))
            .filter((x) => x.d >= 300 && x.d <= 1300)
            .sort((a, b) => a.d - b.d)
            .slice(0, 3);
          const res = await Promise.all(
            dests.map(({ p }) =>
              j<{ coolest: Route }>("/api/route", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({
                  city: cityId,
                  mode: "walk",
                  origin: { lat: hotel.lat, lon: hotel.lon, node: hotel.node },
                  dest: { lat: p.lat, lon: p.lon, node: p.node },
                  depart_at: departIso,
                  date_key: hero.date_id,
                  lambdas: [0, 1, 3],
                }),
              }),
            ),
          );
          res.forEach((r, i) => {
            if (r?.coolest) hotelWalks.push({ dest: dests[i]!.p.name, route: r.coolest });
          });
        }
        set({ progress: 0.75 });

        const buildings = city.buildings;
        const heroGeo = {
          fastest: routeGeo(hero.fastest, buildings),
          coolest: routeGeo(hero.coolest, buildings),
        };
        const scenarioGeo: FilmData["scenarioGeo"] = {};
        for (const s of scenarios)
          scenarioGeo[s.id] =
            s.id === hero.id
              ? heroGeo
              : { fastest: routeGeo(s.fastest, buildings), coolest: routeGeo(s.coolest, buildings) };
        const street = pickStreet(hero.coolest);
        let acLinkArea: FilmData["acLinkArea"] = null;
        if (city.graph) {
          const e = city.graph.raw.edges;
          let sx = 0, sz = 0, n = 0, x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
          for (let i = 0; i < e.u.length; i++) {
            if (e.cls[i] !== "ac_link") continue;
            const g = e.geom[i] ?? [];
            for (let k = 0; k + 1 < g.length; k += 2) {
              sx += g[k]!; sz += g[k + 1]!; n++;
              x0 = Math.min(x0, g[k]!); x1 = Math.max(x1, g[k]!);
              z0 = Math.min(z0, g[k + 1]!); z1 = Math.max(z1, g[k + 1]!);
            }
          }
          if (n) acLinkArea = { x: sx / n, z: sz / n, ext: Math.max(x1 - x0, z1 - z0, 120) };
        }
        const burj =
          (meta as unknown as { max_building_height_m?: number }).max_building_height_m ?? 828;

        const data: FilmData = {
          meta,
          hero,
          scenarios,
          heroGeo,
          scenarioGeo,
          labelSegs: street.labelSegs,
          streetFocus: street.focus,
          replays,
          weather,
          tests,
          shadeBakeLog: bake?.build_log ?? [],
          acLink: sc?.ac_link_story ?? null,
          acLinkArea,
          hotelWalks,
          hotelName: hotel?.name ?? null,
          notes: notes ?? {},
          hasFieldTest: field !== null,
          policy,
          bakedCities: (cities ?? []).filter((c) => c.status === "ready").map((c) => ({
            id: c.id,
            name: c.name,
            lat: c.origin?.lat ?? meta.origin.lat,
            lon: c.origin?.lon ?? meta.origin.lon,
          })),
          burjH: burj,
        };
        set({ data, status: "ready", progress: 1 });
      } catch (e) {
        inflight = null;
        set({ status: "error", error: e instanceof Error ? e.message : String(e) });
      }
    })();
    void get;
    return inflight;
  },
}));
