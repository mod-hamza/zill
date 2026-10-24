// FilmData loader (PRD 14.1): fetched ONCE behind the loading screen. Every number the Film shows
// comes from these payloads (API = real engine output; /film-data/* = verbatim copies of
// backend/replay/*.json, data/test_results.json, docs/SPEAKER_NOTES.md made by
// scripts/sync-film-data.mjs because the API has no endpoint for replay bodies).
import { create } from "zustand";
import type { Object3D } from "three";
import { api, type CityMeta, type Route, type RouteResponse, type ScenariosJson } from "@/lib/api";
import { assetUrl } from "@/lib/assets";
import { routePolyline } from "@/lib/routeGeom";
import { DEFAULT_TZ, hhmmToMinutes, localIso } from "@/lib/sun";
import { useCity } from "@/state/city";
import { SHADE_ROUTE } from "./chapters/directions";
import { authorFlyPath } from "@/three/AppDrivers";
import type { V3 } from "@/three/rigs";
import type {
  AcLinkStory,
  BuildLogRow,
  CaseStudy,
  CaseStudyJson,
  Directions,
  Facts,
  FilmData,
  HeroScenario,
  HotelWalk,
  Replay,
  RouteGeo,
  RouteSet,
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
  // camera on the side away from the Burj: the tower cluster sits behind the street, not in front
  void dir;
  const away = (Math.atan2(cx, -cz) * 180) / Math.PI;
  return { labelSegs, focus: { x: cx, z: cz, bearing: away } };
}

const sameRoute = (a: Route, b: Route) =>
  Math.abs(a.stats.sun_exposure_s - b.stats.sun_exposure_s) < 1 &&
  Math.abs(a.stats.distance_m - b.stats.distance_m) < 1;

/** documented rule for the Ch.8 pair (also in docs/DECISIONS.md) */
export const DIRECTIONS_RULE =
  "First Dubai sun scenario (hero.json `sun`, in file order) whose shade-mode best route differs from its fastest route";

/**
 * Ch.8 "Two directions": for each Dubai sun scenario in file order, ask the engine for the
 * shade-mode routes of the SAME trip at the SAME minute; take the first scenario where shade mode
 * actually picks a different street from the fastest (so both directions are visible).
 */
async function loadDirections(
  cityId: string,
  meta: CityMeta,
  sunScenarios: HeroScenario[],
): Promise<Directions | null> {
  if (!sunScenarios.length) return null;
  for (const sc of sunScenarios) {
    if (!sc.sunniest) continue;
    const dateIso = meta.dates[sc.date_id] ?? sc.date_id;
    const departIso = localIso(dateIso, hhmmToMinutes(sc.depart), meta.timezone || DEFAULT_TZ);
    const r = await j<{ coolest?: Route; best?: Route }>("/api/route", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        city: cityId,
        mode: sc.mode,
        origin: { lat: sc.origin.lat, lon: sc.origin.lon, node: sc.origin.node },
        dest: { lat: sc.dest.lat, lon: sc.dest.lon, node: sc.dest.node },
        depart_at: departIso,
        date_key: sc.date_id,
        lambdas: [0, 1, 3],
        preference: "shade",
      }),
    });
    const shade = r?.coolest ?? r?.best ?? null;
    if (shade && !sameRoute(shade, sc.fastest)) return { scenario: sc, shade, rule: DIRECTIONS_RULE };
  }
  const first = sunScenarios.find((s) => s.sunniest) ?? null;
  return first ? { scenario: first, shade: null, rule: DIRECTIONS_RULE } : null;
}

function setFrom(
  sc: HeroScenario,
  city: string,
  fastest: Route,
  coolest: Route,
  preference: "shade" | "sun",
  filmColors?: RouteSet["filmColors"],
): RouteSet {
  return {
    fastest,
    balanced: sc.balanced,
    coolest,
    preference,
    origin: sc.origin,
    dest: sc.dest,
    date_key: sc.date_id,
    city,
    ...(filmColors ? { filmColors } : {}),
  };
}

/**
 * Short cut "Case studies": the numbers are case_studies.json's (verbatim); the drawn routes are
 * the engine's for the same trip (/api/route at load, same origin/destination/minute/mode/
 * preference). Loops (runs) draw their outbound leg. Dubai cases first, then Oslo (one city switch).
 */
async function loadCases(
  list: CaseStudyJson[],
  geoFor: (cityId: string) => Object3D | null,
  routeSets: Record<string, RouteSet>,
  scenarioGeo: FilmData["scenarioGeo"],
  cityTz: Record<string, string>,
): Promise<CaseStudy[]> {
  const ordered = [...list].sort((a, b) => Number(a.city !== FILM_HOME) - Number(b.city !== FILM_HOME));
  const res = await Promise.all(
    ordered.map((c) =>
      j<RouteResponse>("/api/route", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          city: c.city,
          mode: c.mode,
          origin: { lat: c.origin.lat, lon: c.origin.lon, node: c.origin.node },
          dest: { lat: c.dest.lat, lon: c.dest.lon, node: c.dest.node },
          depart_at: c.depart_iso ?? localIso(c.date ?? c.date_id, hhmmToMinutes(c.depart), cityTz[c.city] ?? DEFAULT_TZ),
          date_key: c.date_id,
          lambdas: [0, 1, 3],
          preference: c.preference,
        }),
      }),
    ),
  );
  return ordered.map((c, i) => {
    const r = res[i];
    const best = c.preference === "sun" ? (r?.sunniest ?? r?.best) : (r?.coolest ?? r?.best);
    if (!r?.fastest || !best) return { c, routeKey: null };
    const key = `case_${c.id}`;
    routeSets[key] = {
      fastest: r.fastest,
      balanced: r.balanced ?? best,
      coolest: best,
      preference: c.preference,
      origin: r.origin,
      dest: r.dest,
      date_key: c.date_id,
      city: c.city,
    };
    const b = geoFor(c.city);
    scenarioGeo[key] = { fastest: routeGeo(r.fastest, b), coolest: routeGeo(best, b) };
    return { c, routeKey: key };
  });
}
const FILM_HOME = "dubai_downtown";

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
        const [replayList, weather, tests, bake, notes, field, cities, facts, caseJson] = await Promise.all([
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
          manifest.includes("facts.json") ? j<Facts>("/film-data/facts.json") : Promise.resolve(null),
          manifest.includes("case_studies.json")
            ? j<{ cases?: CaseStudyJson[] }>("/film-data/case_studies.json")
            : Promise.resolve(null),
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
        set({ progress: 0.7 });

        // Ch.8 "Two directions" (Dubai sun scenarios + engine shade routes for the same trips)
        const sunScenarios = ((sc?.sun?.scenarios ?? []) as HeroScenario[]).filter((s) => !!s.sunniest);
        const directions = await loadDirections(cityId, meta, sunScenarios);
        // Ch.9 "Winter in Oslo": the baked second city, its hero_oslo.json winter sun scenario
        const OSLO = "oslo";
        let oslo: FilmData["oslo"] = null;
        if ((cities ?? []).some((c) => c.id === OSLO && c.status === "ready")) {
          const [om, os] = await Promise.all([
            j<CityMeta>(assetUrl(OSLO, "meta.json")),
            api.scenarios(OSLO),
          ]);
          const list = ((os?.sun?.scenarios ?? []) as HeroScenario[]).filter((s) => !!s.sunniest);
          const winter = list.find((s) => s.date_id === "winter") ?? list[0];
          if (om && winter) {
            oslo = { meta: om, scenario: winter };
            // warm the browser cache so the city switch inside the Film is quick (no await)
            for (const f of ["buildings.glb", "graph.json", "trees.json", "pois.json", `shade/${winter.date_id}/index.json`])
              void fetch(assetUrl(OSLO, f)).catch(() => null);
          }
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
        // extra route sets (Ch.8 / Ch.9) and their geometry for travellers and framing
        const routeSets: Record<string, RouteSet> = {};
        if (directions?.scenario.sunniest) {
          const d = directions.scenario;
          const sun = d.sunniest!;
          routeSets.dir_sun = setFrom(d, cityId, d.fastest, sun, "sun");
          scenarioGeo.dir_sun = { fastest: routeGeo(d.fastest, buildings), coolest: routeGeo(sun, buildings) };
          if (directions.shade) {
            routeSets.dir_shade = setFrom(d, cityId, d.fastest, directions.shade, "shade", { coolest: SHADE_ROUTE });
            routeSets.dir_both = setFrom(d, cityId, directions.shade, sun, "sun", { fastest: SHADE_ROUTE });
            scenarioGeo.dir_shade = { fastest: scenarioGeo.dir_sun.fastest, coolest: routeGeo(directions.shade, buildings) };
            scenarioGeo.dir_both = { fastest: scenarioGeo.dir_shade.coolest, coolest: scenarioGeo.dir_sun.coolest };
          }
        }
        if (oslo?.scenario.sunniest) {
          const o = oslo.scenario;
          routeSets.oslo_sun = setFrom(o, OSLO, o.fastest, o.sunniest!, "sun");
          // Oslo buildings are not loaded yet: flat fly paths (the chapter uses aerial shots only)
          scenarioGeo.oslo_sun = { fastest: routeGeo(o.fastest, null), coolest: routeGeo(o.sunniest!, null) };
        }
        const cases = await loadCases(
          (caseJson?.cases ?? []).filter((c) => c.city === cityId || (c.city === OSLO && !!oslo)),
          (id) => (id === cityId ? buildings : null),
          routeSets,
          scenarioGeo,
          { [cityId]: meta.timezone || DEFAULT_TZ, ...(oslo ? { [OSLO]: oslo.meta.timezone || DEFAULT_TZ } : {}) },
        );
        set({ progress: 0.85 });
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
          directions,
          oslo,
          routeSets,
          cityDates: {
            [cityId]: meta.dates,
            ...(oslo ? { [OSLO]: oslo.meta.dates } : {}),
          },
          facts: facts ?? null,
          cases,
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
