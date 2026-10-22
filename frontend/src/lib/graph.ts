// Client-side graph helpers: parse the columnar graph.json (CONTRACTS section 3) and snap clicks
// to the nearest graph node with a uniform-grid spatial index (no deps).
import type { GraphJson, Mode } from "./api";

export class CityGraph {
  readonly n: number;
  readonly x: Float64Array;
  readonly z: Float64Array;
  readonly lat: Float64Array;
  readonly lon: Float64Array;
  /** bit 1 = walk, 2 = cycle, 4 = scooter (node touches an edge allowing that mode) */
  readonly modeMask: Uint8Array;
  private readonly cell = 50;
  private readonly buckets = new Map<number, number[]>();

  constructor(readonly raw: GraphJson) {
    const nx = raw.nodes.x;
    this.n = nx.length;
    this.x = Float64Array.from(nx);
    this.z = Float64Array.from(raw.nodes.z);
    this.lat = Float64Array.from(raw.nodes.lat);
    this.lon = Float64Array.from(raw.nodes.lon);
    this.modeMask = new Uint8Array(this.n);
    const e = raw.edges;
    for (let i = 0; i < e.u.length; i++) {
      const m =
        (e.walk[i] ? 1 : 0) |
        (e.cycle[i] ? 2 : 0) |
        ((e.scooter?.[i] ?? e.cycle[i]) ? 4 : 0);
      const u = e.u[i]!;
      const v = e.v[i]!;
      this.modeMask[u] = this.modeMask[u]! | m;
      this.modeMask[v] = this.modeMask[v]! | m;
    }
    for (let i = 0; i < this.n; i++) {
      const k = this.key(
        Math.floor(this.x[i]! / this.cell),
        Math.floor(this.z[i]! / this.cell),
      );
      const b = this.buckets.get(k);
      if (b) b.push(i);
      else this.buckets.set(k, [i]);
    }
  }

  private key(cx: number, cz: number): number {
    return (cx + 32768) * 65536 + (cz + 32768);
  }

  /** Nearest node allowing `mode` within `maxDist` metres, or -1. */
  nearest(x: number, z: number, mode: Mode = "walk", maxDist = 400): number {
    const bit = mode === "walk" ? 1 : mode === "cycle" ? 2 : 4;
    const cx = Math.floor(x / this.cell);
    const cz = Math.floor(z / this.cell);
    const rings = Math.ceil(maxDist / this.cell);
    let best = -1;
    let bestD = maxDist * maxDist;
    for (let r = 0; r <= rings; r++) {
      for (let dx = -r; dx <= r; dx++) {
        for (let dz = -r; dz <= r; dz++) {
          if (Math.max(Math.abs(dx), Math.abs(dz)) !== r) continue;
          const b = this.buckets.get(this.key(cx + dx, cz + dz));
          if (!b) continue;
          for (const i of b) {
            if ((this.modeMask[i]! & bit) === 0) continue;
            const d = (this.x[i]! - x) ** 2 + (this.z[i]! - z) ** 2;
            if (d < bestD) {
              bestD = d;
              best = i;
            }
          }
        }
      }
      // once we have a hit, one more ring is enough to guarantee the true nearest
      if (best >= 0 && (r + 1) * this.cell > Math.sqrt(bestD) + this.cell)
        break;
    }
    return best;
  }
}

/**
 * Flat ribbon data for a set of polylines (local metres), merged into one geometry.
 * Each polyline vertex becomes two vertices sharing the CENTRE position; `offset` (xz) is the
 * unit-half-width offset including a clamped miter, so a vertex shader can choose the width
 * (metric or screen-space minimum). Also returns `side` (-1/+1), `dist` (metres along the line),
 * `width` (metres, per line) and an optional per-vertex scalar `value` (e.g. sun exposure).
 */
export type RibbonLine = { pts: number[]; width: number; values?: number[] };
export type RibbonData = {
  center: Float32Array;
  offset: Float32Array;
  side: Float32Array;
  dist: Float32Array;
  width: Float32Array;
  value: Float32Array;
  index: Uint32Array;
  totalLength: number;
};

export function buildRibbons(
  lines: RibbonLine[],
  y: number,
  continuousDist = false,
): RibbonData {
  let nv = 0;
  let ni = 0;
  for (const l of lines) {
    const n = l.pts.length / 2;
    if (n < 2) continue;
    nv += n * 2;
    ni += (n - 1) * 6;
  }
  const center = new Float32Array(nv * 3);
  const offset = new Float32Array(nv * 2);
  const side = new Float32Array(nv);
  const dist = new Float32Array(nv);
  const width = new Float32Array(nv);
  const value = new Float32Array(nv);
  const index = new Uint32Array(ni);
  let v = 0;
  let k = 0;
  let acc = 0;
  for (const l of lines) {
    const p = l.pts;
    const n = p.length / 2;
    if (n < 2) continue;
    const base = v;
    if (!continuousDist) acc = 0;
    for (let i = 0; i < n; i++) {
      const x = p[2 * i]!;
      const z = p[2 * i + 1]!;
      let tx = 0;
      let tz = 0;
      let d0x = 0;
      let d0z = 0;
      if (i > 0) {
        d0x = x - p[2 * i - 2]!;
        d0z = z - p[2 * i - 1]!;
        const L = Math.hypot(d0x, d0z) || 1e-6;
        acc += L;
        d0x /= L;
        d0z /= L;
        tx += d0x;
        tz += d0z;
      }
      if (i < n - 1) {
        let d1x = p[2 * i + 2]! - x;
        let d1z = p[2 * i + 3]! - z;
        const L = Math.hypot(d1x, d1z) || 1e-6;
        d1x /= L;
        d1z /= L;
        tx += d1x;
        tz += d1z;
        if (i === 0) {
          d0x = d1x;
          d0z = d1z;
        }
      }
      let tl = Math.hypot(tx, tz);
      if (tl < 1e-6) {
        tx = d0x;
        tz = d0z;
        tl = 1;
      }
      tx /= tl;
      tz /= tl;
      const dot = Math.max(0.4, Math.abs(tx * d0x + tz * d0z));
      const m = 1 / dot;
      const nxp = -tz * m;
      const nzp = tx * m;
      const val = l.values ? (l.values[i] ?? 0) : 0;
      for (const s of [1, -1]) {
        center.set([x, y, z], v * 3);
        offset.set([nxp * s, nzp * s], v * 2);
        side[v] = s;
        dist[v] = acc;
        width[v] = l.width;
        value[v] = val;
        v++;
      }
    }
    for (let i = 0; i < n - 1; i++) {
      const a = base + i * 2;
      index.set([a, a + 1, a + 2, a + 1, a + 3, a + 2], k);
      k += 6;
    }
  }
  return { center, offset, side, dist, width, value, index, totalLength: acc };
}
