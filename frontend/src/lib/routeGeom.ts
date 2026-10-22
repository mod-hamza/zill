// Pure helpers over a Route (CONTRACTS section 5): polyline, per-vertex exposure, progress stats.
import type { Route } from "./api";

export type RoutePolyline = {
  /** flat x,z pairs */
  pts: number[];
  /** per-vertex sun fraction (segment value) */
  values: number[];
  /** per-vertex class index into segments */
  seg: number[];
  /** cumulative metres at each vertex */
  cum: number[];
  length: number;
};

export function routePolyline(r: Route): RoutePolyline {
  const pts: number[] = [];
  const values: number[] = [];
  const seg: number[] = [];
  const cum: number[] = [];
  let acc = 0;
  r.segments.forEach((s, si) => {
    s.geometry.forEach(([x, z], k) => {
      const n = pts.length / 2;
      if (n > 0) {
        const px = pts[pts.length - 2]!;
        const pz = pts[pts.length - 1]!;
        const d = Math.hypot(x - px, z - pz);
        if (d < 0.05) {
          // shared joint: the vertex takes the value of the segment it starts
          if (k === 0) {
            values[n - 1] = s.sun;
            seg[n - 1] = si;
          }
          return;
        }
        acc += d;
      }
      pts.push(x, z);
      values.push(s.sun);
      seg.push(si);
      cum.push(acc);
    });
  });
  return { pts, values, seg, cum, length: acc };
}

/** Point (x, z) and heading at distance d along the polyline. */
export function pointAt(
  p: RoutePolyline,
  d: number,
): { x: number; z: number; i: number } {
  const n = p.cum.length;
  if (n === 0) return { x: 0, z: 0, i: 0 };
  if (d <= 0) return { x: p.pts[0]!, z: p.pts[1]!, i: 0 };
  if (d >= p.length)
    return { x: p.pts[2 * n - 2]!, z: p.pts[2 * n - 1]!, i: n - 1 };
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (p.cum[mid]! <= d) lo = mid;
    else hi = mid;
  }
  const t = (d - p.cum[lo]!) / Math.max(1e-6, p.cum[hi]! - p.cum[lo]!);
  return {
    x: p.pts[2 * lo]! + (p.pts[2 * hi]! - p.pts[2 * lo]!) * t,
    z: p.pts[2 * lo + 1]! + (p.pts[2 * hi + 1]! - p.pts[2 * lo + 1]!) * t,
    i: lo,
  };
}

export type Progress = {
  elapsedS: number;
  sunS: number;
  shadePct: number;
  segIndex: number;
  cls: string;
};

/**
 * Travel progress at fraction `f` of the route's DURATION, from the route's own segment timings
 * (arrival_s, t_s, sun) — the same numbers the API computed; nothing estimated here.
 */
export function progressAt(r: Route, f: number): Progress {
  const total = r.stats.duration_s;
  const tNow = Math.max(0, Math.min(1, f)) * total;
  let sun = 0;
  let segIndex = 0;
  let cls = "open";
  for (let i = 0; i < r.segments.length; i++) {
    const s = r.segments[i]!;
    const t0 = s.arrival_s;
    const t1 = s.arrival_s + s.t_s;
    if (tNow >= t1) {
      sun += s.t_s * s.sun;
      continue;
    }
    if (tNow > t0) sun += (tNow - t0) * s.sun;
    segIndex = i;
    cls = s.cls;
    break;
  }
  if (tNow >= total && r.segments.length) {
    segIndex = r.segments.length - 1;
    cls = r.segments[segIndex]!.cls;
  }
  const shadePct = tNow > 0 ? 100 * (1 - sun / tNow) : 100;
  return { elapsedS: tNow, sunS: sun, shadePct, segIndex, cls };
}

/** Distance along the polyline at which segment `si` starts, given elapsed time inside it. */
export function distanceAtTime(r: Route, p: RoutePolyline, f: number): number {
  const total = r.stats.duration_s;
  const tNow = Math.max(0, Math.min(1, f)) * total;
  // map time -> distance piecewise through segments (speeds differ on stairs / indoor etc.)
  let segStartD = 0;
  for (let i = 0; i < r.segments.length; i++) {
    const s = r.segments[i]!;
    let len = 0;
    for (let k = 1; k < s.geometry.length; k++)
      len += Math.hypot(
        s.geometry[k]![0] - s.geometry[k - 1]![0],
        s.geometry[k]![1] - s.geometry[k - 1]![1],
      );
    const t1 = s.arrival_s + s.t_s;
    if (tNow <= t1 || i === r.segments.length - 1) {
      const u =
        s.t_s > 0 ? Math.max(0, Math.min(1, (tNow - s.arrival_s) / s.t_s)) : 1;
      return Math.min(p.length, segStartD + len * u);
    }
    segStartD += len;
  }
  return p.length;
}
