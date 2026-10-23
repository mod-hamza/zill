// Pure helpers used by chapter functions. All values derive from FilmData (engine output).
import { colors } from "@/design/tokens";
import type { Route } from "@/lib/api";
import { distanceAtTime, pointAt, progressAt } from "@/lib/routeGeom";
import { hhmmToMinutes, minutesToHHMM } from "@/lib/sun";
import { presetFrom } from "@/three/sceneConfig";
import { flyRig, type RigState, type V3 } from "@/three/rigs";
import type { FilmData, HudState, RouteGeo } from "./types";

export const departMinutes = (depart: string) => hhmmToMinutes(depart);
export const hhmm = (m: number) => minutesToHHMM(m, ":");

/** Traveller on a route at fraction `f` of its DURATION: distance fraction + progress stats. */
export function travel(geo: RouteGeo, f: number) {
  const r = geo.route;
  const p = progressAt(r, f);
  const d = distanceAtTime(r, geo.poly, f);
  const at = geo.poly.length > 0 ? d / geo.poly.length : 0;
  // sun counter that ends EXACTLY on stats.sun_exposure_s (segment sums can differ by rounding)
  const total = progressAt(r, 1).sunS;
  const sunS = total > 0 ? (p.sunS / total) * r.stats.sun_exposure_s : 0;
  const shadePct = p.elapsedS > 0 ? 100 * (1 - sunS / p.elapsedS) : 100;
  return { at, d, elapsedS: p.elapsedS, sunS, shadePct, cls: p.cls, seg: p.segIndex };
}

export function hudFor(
  data: FilmData,
  geo: RouteGeo,
  f: number,
  departMin: number,
  withFeel = true,
): HudState {
  const tr = travel(geo, f);
  const w = data.weather;
  return {
    sunS: tr.sunS,
    shadePct: f <= 0 ? 100 : f >= 1 ? geo.route.stats.shaded_pct : tr.shadePct,
    clock: hhmm(departMin + tr.elapsedS / 60),
    feel: withFeel ? (w?.apparent_c ?? null) : undefined,
    feelBadge: withFeel ? weatherBadge(data) : undefined,
    cls: tr.cls,
  };
}

export function weatherBadge(data: FilmData): string {
  const w = data.weather;
  if (!w) return "Weather unavailable";
  if (w.source === "synthetic_representative") return "Representative profile";
  return w.label ?? w.source ?? "Weather";
}

/** Point on the route polyline at distance d (m), with a heading (rad, from north clockwise). */
export function routePoint(geo: RouteGeo, d: number) {
  const a = pointAt(geo.poly, Math.max(0, d));
  const b = pointAt(geo.poly, Math.min(geo.poly.length, d + 12));
  const c = pointAt(geo.poly, Math.max(0, d - 12));
  const hx = b.x - c.x;
  const hz = b.z - c.z;
  return { x: a.x, z: a.z, heading: Math.atan2(hx, -hz) };
}

/** Chase camera behind the traveller (low aerial), looking at the traveller. */
export function chaseCam(
  geo: RouteGeo,
  d: number,
  back = 70,
  up = 45,
  fov = 34,
  side = 0.35,
): RigState {
  const p = routePoint(geo, d);
  // average heading over a longer window so the camera does not whip at corners
  const ahead = pointAt(geo.poly, Math.min(geo.poly.length, d + 60));
  const behind = pointAt(geo.poly, Math.max(0, d - 60));
  const h = Math.atan2(ahead.x - behind.x, -(ahead.z - behind.z)) + side;
  const pos: V3 = [p.x - Math.sin(h) * back, up, p.z + Math.cos(h) * back];
  return { position: pos, target: [p.x, 2, p.z], fov, roll: 0 };
}

/** Eye-level fly camera at distance fraction `u` of the authored fly path. */
export function flyCam(geo: RouteGeo, u: number, durationS: number): RigState {
  return flyRig(u, {
    points: geo.fly,
    lookahead: 34,
    lookDrop: -1.2,
    fov: 40,
    accel: 0.001,
    floatAmp: 0.08,
    seed: 6,
    durationS,
  });
}

/** Three-quarter aerial framing a route bbox (long lens, never top-down). */
export function frameGeo(geo: RouteGeo, bearing = 200, k = 1.25, steep = 0.8, fov = 32): RigState {
  const b = geo.bbox;
  const dist = b.ext * k;
  const p = presetFrom([b.cx, 0, b.cz], bearing, dist, dist * steep, fov);
  return { ...p, roll: 0 };
}

export function lerpRig(a: RigState, b: RigState, u: number): RigState {
  const l = (x: number, y: number) => x + (y - x) * u;
  return {
    position: [l(a.position[0], b.position[0]), l(a.position[1], b.position[1]), l(a.position[2], b.position[2])],
    target: [l(a.target[0], b.target[0]), l(a.target[1], b.target[1]), l(a.target[2], b.target[2])],
    fov: l(a.fov, b.fov),
    roll: l(a.roll, b.roll),
  };
}

export const routeColor = { fastest: colors.slate, coolest: colors.brass, balanced: colors.bronze };

export function minOf(route: Route) {
  return route.stats.duration_s / 60;
}

/** minutes with one decimal (presentation formatting of computed seconds) */
export const fmt1 = (s: number) => (s / 60).toFixed(1);
