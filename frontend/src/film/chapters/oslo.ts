// Ch.9 "Winter in Oslo." (56 s design) — the second city, baked by the same open-data pipeline.
// The Film switches the shared scene to Oslo (FrameState.city). 21 December: a time-lapse of the
// real low sun over the core (long shadows), then hero_oslo.json's winter sun scenario (fastest
// slate vs sunniest ember, two walkers on one clock), its numbers, and the honest note: at a 6°
// sun the UV index is ~0, so this is daylight and mood, not vitamin D. Every number is the data's.
import { colors } from "@/design/tokens";
import { orbitRig, type RigState } from "@/three/rigs";
import { ramp, rampIO, rampUI, win } from "../ease";
import { departMinutes, frameGeo, lerpRig, travel } from "../helpers";
import type { ChapterFn, ChapterOut, FilmData } from "../types";

export const OSLO_DUR = 56;
export const OSLO_CITY = "oslo";
export const OSLO = { lapse0: 2, lapse1: 17, route0: 19, walk0: 24, walk1: 38, note0: 39 } as const;
/** the time-lapse starts this long before the scenario's departure (min) */
const LAPSE_LEAD_MIN = 150;

function core(data: FilmData) {
  const g = (data.oslo?.meta as unknown as { core_grid?: { x0: number; z0: number; rows: number; cols: number; res_m: number } })
    ?.core_grid;
  if (!g) return { cx: 0, cz: 0, ext: 2000 };
  const w = g.cols * g.res_m;
  const h = g.rows * g.res_m;
  return { cx: g.x0 + w / 2, cz: g.z0 + h / 2, ext: Math.max(w, h) };
}

const establishing = (data: FilmData, u: number): RigState => {
  const c = core(data);
  // low, long lens from the south-west so the long December shadows run towards camera-right
  return orbitRig(u, {
    target: [c.cx, 0, c.cz],
    radius: c.ext * 0.78,
    height: c.ext * 0.36,
    startDeg: 206,
    sweepDeg: 16,
    fov: 33,
    floatAmp: 0.1,
    seed: 15,
    durationS: OSLO_DUR,
  });
};

/** "2026-12-21" -> "21 December" */
export function longDate(iso: string): string {
  const m = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const [, mo, d] = iso.split("-").map(Number);
  return mo && d ? `${d} ${m[mo - 1]}` : iso;
}

export function osloCaption(data: FilmData): string | null {
  const o = data.oslo;
  const w = o?.scenario.wellbeing?.daylight_window;
  if (!o || !w) return null;
  const date = longDate(o.meta.dates[o.scenario.date_id] ?? o.scenario.date_id);
  return `${date}, ${o.scenario.depart}. The sun is ${w.sun_alt_deg.toFixed(1)}° high. ${w.shadow_text}`;
}

export const oslo: ChapterFn = (t, data) => {
  const s = t * OSLO_DUR;
  const out: ChapterOut = {
    city: OSLO_CITY,
    look: 1,
    routeWidth: 1.9,
    overlays: [{ kind: "title", text: "Winter in Oslo.", opacity: win(s, 0.6, 4.6, 1, 1), size: "card" }],
  };
  const o = data.oslo;
  const geo = data.scenarioGeo.oslo_sun;
  if (!o || !geo) {
    out.overlays!.push({ kind: "honest", text: "Oslo is not baked on this machine.", opacity: win(s, 5, OSLO_DUR + 1, 1, 0.01) });
    return out;
  }
  const sc = o.scenario;
  const dep = departMinutes(sc.depart);
  const lapse = dep - LAPSE_LEAD_MIN + LAPSE_LEAD_MIN * rampIO(s, OSLO.lapse0, OSLO.lapse1);

  // camera: establishing orbit, then ease onto the walk
  const routeCam = lerpRig(frameGeo(geo.coolest, 204, 1.25, 0.8, 32), frameGeo(geo.coolest, 214, 1.15, 0.78, 32), ramp(s, OSLO.route0, OSLO_DUR));
  out.camera = lerpRig(establishing(data, ramp(s, 0, OSLO.route0 + 2)), routeCam, rampIO(s, OSLO.route0 - 2, OSLO.route0 + 4));

  const durF = geo.fastest.route.stats.duration_s;
  const durS = geo.coolest.route.stats.duration_s;
  const T = Math.max(durF, durS) * rampIO(s, OSLO.walk0, OSLO.walk1);
  out.sun = { dateKey: sc.date_id, minutes: s < OSLO.walk0 ? lapse : dep + T / 60 };
  out.routes = {
    result: s > OSLO.route0 - 1 ? "oslo_sun" : null,
    view: "presentation",
    selected: "coolest",
    reveal: { fastest: rampUI(s, OSLO.route0, OSLO.route0 + 2.5), coolest: rampUI(s, OSLO.route0 + 1.2, OSLO.route0 + 4.5) },
    opacity: win(s, OSLO.route0 - 0.5, OSLO_DUR + 1, 0.6, 0.01),
  };
  if (s >= OSLO.walk0 - 0.5)
    out.travellers = [
      { key: "fastest", scenario: "oslo_sun", at: travel(geo.fastest, Math.min(1, T / durF)).at, color: colors.slate },
      { key: "coolest", scenario: "oslo_sun", at: travel(geo.coolest, Math.min(1, T / durS)).at, color: colors.ember },
    ];

  const ov = out.overlays!;
  const cap = osloCaption(data);
  if (cap) ov.push({ kind: "caption", text: cap, opacity: win(s, 6, 17.5, 1.2, 1.2), align: "left" });
  ov.push({ kind: "oslo", opacity: win(s, OSLO.route0 + 2, OSLO_DUR + 1, 1, 0.01), progress: ramp(s, OSLO.route0 + 2, OSLO.route0 + 8) });
  if (sc.wellbeing) ov.push({ kind: "wellbeing", which: "oslo", opacity: win(s, OSLO.note0, OSLO_DUR + 1, 1.2, 0.01) });
  const uv = sc.wellbeing?.uv;
  if (uv?.index !== null && uv?.index !== undefined)
    ov.push({
      kind: "caption",
      text: `Daylight and mood, not vitamin D: UV ${uv.index.toFixed(1)}.`,
      opacity: win(s, OSLO.note0 + 1.5, OSLO_DUR + 1, 1.2, 0.01),
      align: "left",
    });
  return out;
};
