// Synthetic dev fixture for the SCENE stream (public/dev-fixture/). NOT real data: used only until
// the real Downtown Dubai bake lands; deleted before the Phase 6 gate. Everything it produces is
// labelled `synthetic: true` and the UI shows "Synthetic fixture".
//
// Run: npx tsx scripts/qa-make-fixture.ts
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { deflateSync } from "node:zlib";
import { sunAt, sunTimesMinutes, minutesToHHMM } from "../src/lib/sun";
import { to_wgs84 } from "../src/lib/geo";

const OUT = join(__dirname, "..", "public", "dev-fixture");
const ORIGIN = { lat: 25.1972, lon: 55.2744 };
const RES = 2;
const HALF = 700; // core grid covers [-700, 700]^2
const COLS = (2 * HALF) / RES;
const ROWS = COLS;
const X0 = -HALF;
const Z0 = -HALF;
const PED_H = 1.5;

let seed = 7;
const rnd = () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
};

// ---------------------------------------------------------------- buildings (boxes)
type Box = {
  id: number;
  x0: number;
  z0: number;
  x1: number;
  z1: number;
  ymin: number;
  h: number;
  name?: string;
};
const boxes: Box[] = [];
let bid = 0;
// the "tower": 3 stacked setback boxes sharing one building id (828 m total)
const tower = bid++;
boxes.push({
  id: tower,
  x0: -35,
  z0: -35,
  x1: 35,
  z1: 35,
  ymin: 0,
  h: 420,
  name: "Synthetic tower",
});
boxes.push({ id: tower, x0: -22, z0: -22, x1: 22, z1: 22, ymin: 420, h: 650 });
boxes.push({ id: tower, x0: -8, z0: -8, x1: 8, z1: 8, ymin: 650, h: 828 });
const STREET = 100; // street grid spacing
const ROAD_W = 22;
for (let gx = -600; gx < 600; gx += STREET) {
  for (let gz = -600; gz < 600; gz += STREET) {
    const bx0 = gx + ROAD_W / 2;
    const bz0 = gz + ROAD_W / 2;
    const bx1 = gx + STREET - ROAD_W / 2;
    const bz1 = gz + STREET - ROAD_W / 2;
    if (bx1 > -60 && bx0 < 60 && bz1 > -60 && bz0 < 60) continue; // tower plot
    if (gx === 100 && gz === 0) continue; // a "plaza" block (open)
    const split = rnd() < 0.5 ? 1 : 2;
    const w = (bx1 - bx0) / split;
    for (let i = 0; i < split; i++) {
      for (let j = 0; j < split; j++) {
        const inset = 3 + rnd() * 5;
        const tall = rnd() < 0.15;
        const h = tall ? 120 + rnd() * 160 : 18 + rnd() * 55;
        boxes.push({
          id: bid++,
          x0: bx0 + i * w + inset,
          z0: bz0 + j * w + inset,
          x1: bx0 + (i + 1) * w - inset,
          z1: bz0 + (j + 1) * w - inset,
          ymin: 0,
          h,
        });
      }
    }
  }
}

// ---------------------------------------------------------------- trees along two boulevards
const trees: { x: number; z: number; r: number; h: number; src: string }[] = [];
for (let x = -590; x < 590; x += 8) {
  if (Math.abs(x) < 60) continue;
  trees.push({ x, z: -100 + 8, r: 3, h: 7, src: "row" });
  trees.push({ x, z: -100 - 8, r: 3, h: 7, src: "row" });
}
for (let z = -590; z < 590; z += 9) {
  trees.push({ x: 200 + 8, z, r: 3, h: 7, src: "row" });
}

// ---------------------------------------------------------------- graph: street grid
const nodes: { x: number; z: number }[] = [];
const nodeIdx = new Map<string, number>();
const N = (x: number, z: number) => {
  const k = `${x},${z}`;
  let i = nodeIdx.get(k);
  if (i === undefined) {
    i = nodes.length;
    nodes.push({ x, z });
    nodeIdx.set(k, i);
  }
  return i;
};
type E = {
  u: number;
  v: number;
  cls: string;
  highway: string;
  name: string | null;
};
const edges: E[] = [];
for (let x = -600; x <= 600; x += STREET) {
  for (let z = -600; z <= 600; z += STREET / 2) {
    if (z + STREET / 2 <= 600)
      edges.push({
        u: N(x, z),
        v: N(x, z + STREET / 2),
        cls: "open",
        highway: "footway",
        name: `Avenue ${x}`,
      });
  }
}
for (let z = -600; z <= 600; z += STREET) {
  for (let x = -600; x <= 600; x += STREET / 2) {
    if (x + STREET / 2 <= 600)
      edges.push({
        u: N(x, z),
        v: N(x + STREET / 2, z),
        cls: "open",
        highway: z === -100 ? "pedestrian" : "footway",
        name: z === -100 ? "Boulevard" : `Street ${z}`,
      });
  }
}
// a covered colonnade and an AC link
edges.forEach((e) => {
  const a = nodes[e.u]!;
  const b = nodes[e.v]!;
  if (a.z === 200 && b.z === 200 && a.x >= -300 && b.x <= -100)
    e.cls = "covered";
  if (a.x === 300 && b.x === 300 && a.z >= -300 && b.z <= -200)
    e.cls = "ac_link";
});

// ---------------------------------------------------------------- shade raster
function shadeRaster(altDeg: number, azDeg: number): Uint8Array {
  const out = new Uint8Array(ROWS * COLS);
  if (altDeg <= 2) return out;
  const f = new Float32Array(ROWS * COLS).fill(1);
  const az = (azDeg * Math.PI) / 180;
  const k = 1 / Math.tan((altDeg * Math.PI) / 180);
  const sx = -Math.sin(az); // shadow direction = away from the sun
  const sz = Math.cos(az);
  const fillPoly = (pts: [number, number][], mulBy: number) => {
    const hull = convexHull(pts);
    let zmin = Infinity,
      zmax = -Infinity;
    for (const p of hull) {
      zmin = Math.min(zmin, p[1]);
      zmax = Math.max(zmax, p[1]);
    }
    const r0 = Math.max(0, Math.floor((zmin - Z0) / RES));
    const r1 = Math.min(ROWS - 1, Math.ceil((zmax - Z0) / RES));
    for (let r = r0; r <= r1; r++) {
      const zc = Z0 + (r + 0.5) * RES;
      let xl = Infinity,
        xr = -Infinity;
      for (let i = 0; i < hull.length; i++) {
        const [ax, az2] = hull[i]!;
        const [bx, bz] = hull[(i + 1) % hull.length]!;
        if ((az2 <= zc && bz > zc) || (bz <= zc && az2 > zc)) {
          const x = ax + ((zc - az2) / (bz - az2)) * (bx - ax);
          xl = Math.min(xl, x);
          xr = Math.max(xr, x);
        }
      }
      if (xl > xr) continue;
      const c0 = Math.max(0, Math.ceil((xl - X0) / RES - 0.5));
      const c1 = Math.min(COLS - 1, Math.floor((xr - X0) / RES - 0.5));
      for (let c = c0; c <= c1; c++) f[r * COLS + c] = f[r * COLS + c]! * mulBy;
    }
  };
  for (const b of boxes) {
    const hTop = b.h - PED_H;
    const hBot = Math.max(0, b.ymin - PED_H);
    if (hTop <= 0) continue;
    const pts: [number, number][] = [];
    const corners: [number, number][] = [
      [b.x0, b.z0],
      [b.x1, b.z0],
      [b.x1, b.z1],
      [b.x0, b.z1],
    ];
    for (const [x, z] of corners) {
      pts.push([x + sx * k * hBot, z + sz * k * hBot]);
      pts.push([x + sx * k * hTop, z + sz * k * hTop]);
    }
    fillPoly(pts, 0);
  }
  for (const t of trees) {
    const hc = t.h * 0.7 - PED_H;
    const cx = t.x + sx * k * hc;
    const cz = t.z + sz * k * hc;
    const pts: [number, number][] = [];
    for (let i = 0; i < 12; i++)
      pts.push([
        cx + Math.cos((i / 12) * 2 * Math.PI) * t.r,
        cz + Math.sin((i / 12) * 2 * Math.PI) * t.r,
      ]);
    fillPoly(pts, 0.35);
  }
  for (let i = 0; i < f.length; i++) out[i] = Math.round(f[i]! * 255);
  // building footprints = 0 (ground floor only)
  for (const b of boxes) if (b.ymin === 0) fillMask(out, b);
  return out;
}
function fillMask(out: Uint8Array, b: Box) {
  const c0 = Math.max(0, Math.ceil((b.x0 - X0) / RES - 0.5));
  const c1 = Math.min(COLS - 1, Math.floor((b.x1 - X0) / RES - 0.5));
  const r0 = Math.max(0, Math.ceil((b.z0 - Z0) / RES - 0.5));
  const r1 = Math.min(ROWS - 1, Math.floor((b.z1 - Z0) / RES - 0.5));
  for (let r = r0; r <= r1; r++)
    for (let c = c0; c <= c1; c++) out[r * COLS + c] = 0;
}
function convexHull(p: [number, number][]): [number, number][] {
  const pts = [...p].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (
    o: [number, number],
    a: [number, number],
    b: [number, number],
  ) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  for (const q of pts) {
    while (
      lower.length >= 2 &&
      cross(lower[lower.length - 2]!, lower[lower.length - 1]!, q) <= 0
    )
      lower.pop();
    lower.push(q);
  }
  const upper: [number, number][] = [];
  for (const q of [...pts].reverse()) {
    while (
      upper.length >= 2 &&
      cross(upper[upper.length - 2]!, upper[upper.length - 1]!, q) <= 0
    )
      upper.pop();
    upper.push(q);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

// ---------------------------------------------------------------- PNG writer (8-bit grayscale)
const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const b of buf) c = CRC[(c ^ b) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
function png(gray: Uint8Array, w: number, h: number): Buffer {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = 0; // grayscale
  const raw = Buffer.alloc((w + 1) * h);
  for (let r = 0; r < h; r++) {
    raw[r * (w + 1)] = 0;
    Buffer.from(gray.buffer, gray.byteOffset + r * w, w).copy(
      raw,
      r * (w + 1) + 1,
    );
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ---------------------------------------------------------------- GLB writer (tiles)
function glb(): Buffer {
  const TILE = 250;
  const tiles = new Map<string, Box[]>();
  for (const b of boxes) {
    const k = `${Math.floor((b.x0 + b.x1) / 2 / TILE)}_${Math.floor((b.z0 + b.z1) / 2 / TILE)}`;
    const a = tiles.get(k) ?? [];
    a.push(b);
    tiles.set(k, a);
  }
  const bufs: Buffer[] = [];
  let off = 0;
  const bufferViews: object[] = [];
  const accessors: object[] = [];
  const meshes: object[] = [];
  const nodesJ: object[] = [];
  const pushView = (arr: Float32Array | Uint32Array, target: number) => {
    const b = Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength);
    const pad = (4 - (b.length % 4)) % 4;
    bufs.push(b, Buffer.alloc(pad));
    bufferViews.push({
      buffer: 0,
      byteOffset: off,
      byteLength: b.length,
      target,
    });
    off += b.length + pad;
    return bufferViews.length - 1;
  };
  for (const [k, list] of tiles) {
    const P: number[] = [];
    const Nn: number[] = [];
    const I: number[] = [];
    const H: number[] = [];
    const ID: number[] = [];
    const quad = (
      a: number[],
      b: number[],
      c: number[],
      d: number[],
      n: number[],
      box: Box,
    ) => {
      const base = P.length / 3;
      for (const v of [a, b, c, d]) {
        P.push(...v);
        Nn.push(...n);
        H.push(box.h);
        ID.push(box.id);
      }
      I.push(base, base + 1, base + 2, base, base + 2, base + 3);
    };
    for (const b of list) {
      const y0 = b.ymin,
        y1 = b.h;
      // roof (CCW seen from +y)
      quad(
        [b.x0, y1, b.z0],
        [b.x0, y1, b.z1],
        [b.x1, y1, b.z1],
        [b.x1, y1, b.z0],
        [0, 1, 0],
        b,
      );
      // north (-z)
      quad(
        [b.x1, y0, b.z0],
        [b.x0, y0, b.z0],
        [b.x0, y1, b.z0],
        [b.x1, y1, b.z0],
        [0, 0, -1],
        b,
      );
      // south (+z)
      quad(
        [b.x0, y0, b.z1],
        [b.x1, y0, b.z1],
        [b.x1, y1, b.z1],
        [b.x0, y1, b.z1],
        [0, 0, 1],
        b,
      );
      // west (-x)
      quad(
        [b.x0, y0, b.z0],
        [b.x0, y0, b.z1],
        [b.x0, y1, b.z1],
        [b.x0, y1, b.z0],
        [-1, 0, 0],
        b,
      );
      // east (+x)
      quad(
        [b.x1, y0, b.z1],
        [b.x1, y0, b.z0],
        [b.x1, y1, b.z0],
        [b.x1, y1, b.z1],
        [1, 0, 0],
        b,
      );
    }
    const pos = new Float32Array(P);
    const mn = [Infinity, Infinity, Infinity],
      mx = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < pos.length; i += 3)
      for (let j = 0; j < 3; j++) {
        mn[j] = Math.min(mn[j]!, pos[i + j]!);
        mx[j] = Math.max(mx[j]!, pos[i + j]!);
      }
    const vc = pos.length / 3;
    const acc = (
      view: number,
      type: string,
      count: number,
      comp = 5126,
      extra: object = {},
    ) => {
      accessors.push({
        bufferView: view,
        componentType: comp,
        count,
        type,
        ...extra,
      });
      return accessors.length - 1;
    };
    const aP = acc(pushView(pos, 34962), "VEC3", vc, 5126, {
      min: mn,
      max: mx,
    });
    const aN = acc(pushView(new Float32Array(Nn), 34962), "VEC3", vc);
    const aI = acc(pushView(new Float32Array(ID), 34962), "SCALAR", vc);
    const aH = acc(pushView(new Float32Array(H), 34962), "SCALAR", vc);
    const aX = acc(
      pushView(new Uint32Array(I), 34963),
      "SCALAR",
      I.length,
      5125,
    );
    meshes.push({
      primitives: [
        {
          attributes: {
            POSITION: aP,
            NORMAL: aN,
            _BUILDING_ID: aI,
            _HEIGHT: aH,
          },
          indices: aX,
        },
      ],
    });
    nodesJ.push({ name: `tile_${k}`, mesh: meshes.length - 1 });
  }
  const bin = Buffer.concat(bufs);
  const json = {
    asset: { version: "2.0", generator: "zill qa-make-fixture (synthetic)" },
    scene: 0,
    scenes: [{ nodes: nodesJ.map((_, i) => i) }],
    nodes: nodesJ,
    meshes,
    accessors,
    bufferViews,
    buffers: [{ byteLength: bin.length }],
  };
  let jb = Buffer.from(JSON.stringify(json));
  jb = Buffer.concat([jb, Buffer.alloc((4 - (jb.length % 4)) % 4, 0x20)]);
  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + jb.length + 8 + bin.length, 8);
  const jh = Buffer.alloc(8);
  jh.writeUInt32LE(jb.length, 0);
  jh.writeUInt32LE(0x4e4f534a, 4);
  const bh = Buffer.alloc(8);
  bh.writeUInt32LE(bin.length, 0);
  bh.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, jh, jb, bh, bin]);
}

// ---------------------------------------------------------------- write everything
mkdirSync(OUT, { recursive: true });
const dates: Record<string, string> = {
  winter: "2026-01-15",
  spring: "2026-04-15",
  summer: "2026-07-15",
  hackathon: "2026-10-24",
};
const bakeDates = ["hackathon", "summer"];
const rasters = new Map<string, Uint8Array>();
for (const id of bakeDates) {
  const iso = dates[id]!;
  const st = sunTimesMinutes(iso, ORIGIN.lat, ORIGIN.lon);
  const m0 = Math.floor((st.sunrise - 20) / 10) * 10;
  const m1 = Math.ceil((st.sunset + 20) / 10) * 10;
  const steps = [];
  mkdirSync(join(OUT, "shade", id), { recursive: true });
  for (let m = m0; m <= m1; m += 10) {
    const s = sunAt(iso, m, ORIGIN.lat, ORIGIN.lon);
    const hhmm = minutesToHHMM(m);
    const r = shadeRaster(s.altDeg, s.azDeg);
    rasters.set(`${id}_${hhmm}`, r);
    writeFileSync(
      join(OUT, "shade", id, `step_${hhmm}.png`),
      png(r, COLS, ROWS),
    );
    steps.push({
      hhmm,
      ts: `${iso}T${minutesToHHMM(m, ":")}:00+04:00`,
      alt: +s.altDeg.toFixed(3),
      az: +s.azDeg.toFixed(3),
      night: s.altDeg <= 2,
      file: `step_${hhmm}.png`,
    });
  }
  writeFileSync(
    join(OUT, "shade", id, "index.json"),
    JSON.stringify({ date: iso, date_id: id, steps }),
  );
  console.log(`shade ${id}: ${steps.length} steps`);
}

const lat: number[] = [],
  lon: number[] = [];
for (const n of nodes) {
  const [la, lo] = to_wgs84(n.x, n.z, ORIGIN);
  lat.push(+la.toFixed(7));
  lon.push(+lo.toFixed(7));
}
const graph = {
  nodes: {
    x: nodes.map((n) => n.x),
    z: nodes.map((n) => n.z),
    lat,
    lon,
    entrance: nodes.map(() => false),
    crossing: nodes.map(() => false),
  },
  edges: {
    u: edges.map((e) => e.u),
    v: edges.map((e) => e.v),
    length_m: edges.map((e) =>
      Math.hypot(nodes[e.u]!.x - nodes[e.v]!.x, nodes[e.u]!.z - nodes[e.v]!.z),
    ),
    highway: edges.map((e) => e.highway),
    cls: edges.map((e) => e.cls),
    stairs: edges.map(() => false),
    walk: edges.map(() => true),
    cycle: edges.map(() => true),
    scooter: edges.map(() => true),
    name: edges.map((e) => e.name),
    osm: edges.map(() => "synthetic"),
    geom: edges.map((e) => [
      nodes[e.u]!.x,
      nodes[e.u]!.z,
      nodes[e.v]!.x,
      nodes[e.v]!.z,
    ]),
  },
};
writeFileSync(join(OUT, "graph.json"), JSON.stringify(graph));
writeFileSync(join(OUT, "trees.json"), JSON.stringify({ trees }));
writeFileSync(join(OUT, "buildings.glb"), glb());

const meta = {
  city_id: "dubai_downtown",
  name: "Synthetic fixture",
  synthetic: true,
  timezone: "Asia/Dubai",
  origin: ORIGIN,
  bbox_core: { s: 0, w: 0, n: 0, e: 0 },
  core_grid: { x0: X0, z0: Z0, rows: ROWS, cols: COLS, res_m: RES },
  counts: {
    buildings: new Set(boxes.map((b) => b.id)).size,
    trees: trees.length,
    nodes: nodes.length,
    edges: edges.length,
  },
  max_building_height_m: 828,
  attribution: "Synthetic fixture (not OSM)",
  dates,
};
writeFileSync(join(OUT, "meta.json"), JSON.stringify(meta, null, 1));

// pois: a few named intersections
const poiAt = (id: string, name: string, x: number, z: number) => {
  const node = N(x, z);
  const [la, lo] = to_wgs84(x, z, ORIGIN);
  return {
    id,
    name,
    lat: la,
    lon: lo,
    x,
    z,
    node,
    kind: "landmark",
    source: "synthetic",
  };
};
const pois = [
  poiAt("west_gate", "West Gate (synthetic)", -500, -100),
  poiAt("east_plaza", "East Plaza (synthetic)", 400, 300),
];
writeFileSync(join(OUT, "pois.json"), JSON.stringify({ pois }));

// ---------------------------------------------------------------- fixture routes (Dijkstra)
function sampleSun(r: Uint8Array, x: number, z: number): number {
  const c = Math.min(COLS - 1, Math.max(0, Math.floor((x - X0) / RES)));
  const rr = Math.min(ROWS - 1, Math.max(0, Math.floor((z - Z0) / RES)));
  return r[rr * COLS + c]! / 255;
}
function edgeSun(r: Uint8Array, e: E): number {
  const a = nodes[e.u]!,
    b = nodes[e.v]!;
  if (e.cls !== "open") return 0;
  let s = 0;
  const n = 16;
  // sample the sidewalk 6 m off the centreline on both sides; pedestrians use the shadier one
  const L = Math.hypot(b.x - a.x, b.z - a.z);
  const nx = -(b.z - a.z) / L,
    nz = (b.x - a.x) / L;
  let s1 = 0;
  for (let i = 0; i < n; i++) {
    const t = (i + 0.5) / n;
    const x = a.x + (b.x - a.x) * t,
      z = a.z + (b.z - a.z) * t;
    s += sampleSun(r, x + nx * 6, z + nz * 6);
    s1 += sampleSun(r, x - nx * 6, z - nz * 6);
  }
  return Math.min(s, s1) / n;
}
function dijkstra(
  src: number,
  dst: number,
  cost: (e: E, i: number) => number,
): number[] {
  const adj: [number, number][][] = nodes.map(() => []);
  edges.forEach((e, i) => {
    adj[e.u]!.push([e.v, i]);
    adj[e.v]!.push([e.u, i]);
  });
  const dist = new Float64Array(nodes.length).fill(Infinity);
  const prev = new Int32Array(nodes.length).fill(-1);
  const prevE = new Int32Array(nodes.length).fill(-1);
  dist[src] = 0;
  const done = new Uint8Array(nodes.length);
  for (;;) {
    let u = -1;
    let best = Infinity;
    for (let i = 0; i < nodes.length; i++)
      if (!done[i] && dist[i]! < best) {
        best = dist[i]!;
        u = i;
      }
    if (u < 0 || u === dst) break;
    done[u] = 1;
    for (const [v, ei] of adj[u]!) {
      const d = dist[u]! + cost(edges[ei]!, ei);
      if (d < dist[v]!) {
        dist[v] = d;
        prev[v] = u;
        prevE[v] = ei;
      }
    }
  }
  const path: number[] = [];
  for (let v = dst; v !== src; v = prev[v]!) path.unshift(prevE[v]!);
  return path;
}
const depart = 16 * 60;
const r16 = rasters.get(`hackathon_${minutesToHHMM(depart)}`)!;
function routeFor(label: string, lam: number, src: number, dst: number) {
  const path = dijkstra(src, dst, (e, i) => {
    const L = graph.edges.length_m[i]!;
    return (L / 1.4) * (1 + lam * edgeSun(r16, e));
  });
  let cur = src;
  let tS = 0;
  const segments = [];
  const nodesOut = [src];
  let sunS = 0,
    dist = 0,
    covered = 0;
  for (const ei of path) {
    const e = edges[ei]!;
    const fwd = e.u === cur;
    const a = nodes[fwd ? e.u : e.v]!,
      b = nodes[fwd ? e.v : e.u]!;
    const L = graph.edges.length_m[ei]!;
    const t = L / 1.4;
    const sun = edgeSun(r16, e);
    segments.push({
      edge: ei,
      geometry: [
        [a.x, a.z],
        [b.x, b.z],
      ],
      arrival_s: tS,
      t_s: t,
      sun: +sun.toFixed(3),
      cls: e.cls,
    });
    tS += t;
    sunS += t * sun;
    dist += L;
    if (e.cls !== "open") covered += L;
    cur = fwd ? e.v : e.u;
    nodesOut.push(cur);
  }
  return {
    lambda: lam,
    label,
    mode: "walk",
    depart: `2026-10-24T16:00:00+04:00`,
    stats: {
      distance_m: dist,
      duration_s: tS,
      sun_exposure_s: sunS,
      shaded_pct: 100 * (1 - sunS / tS),
      covered_pct: (100 * covered) / dist,
      indoor_pct: 0,
      rhl: sunS,
      added_time_s: 0,
      sun_saved_s: 0,
      sun_saved_pct: 0,
      rhl_saved_pct: 0,
    },
    nodes: nodesOut,
    edges: path,
    segments,
  };
}
const src = pois[0]!.node,
  dst = pois[1]!.node;
const fastest = routeFor("fastest", 0, src, dst);
const balanced = routeFor("balanced", 1, src, dst);
const coolest = routeFor("coolest", 3, src, dst);
for (const r of [balanced, coolest]) {
  r.stats.added_time_s = r.stats.duration_s - fastest.stats.duration_s;
  r.stats.sun_saved_s = fastest.stats.sun_exposure_s - r.stats.sun_exposure_s;
  r.stats.sun_saved_pct =
    (100 * r.stats.sun_saved_s) / Math.max(1, fastest.stats.sun_exposure_s);
  r.stats.rhl_saved_pct = r.stats.sun_saved_pct;
}
const hero = {
  generated_at: new Date().toISOString(),
  synthetic: true,
  scenarios: [
    {
      id: "tourist_walk",
      persona: "tourist",
      mode: "walk",
      origin: pois[0],
      dest: pois[1],
      date_id: "hackathon",
      depart: "16:00",
      fastest,
      balanced,
      coolest,
      departure: null,
    },
  ],
};
writeFileSync(join(OUT, "hero.json"), JSON.stringify(hero));
console.log(
  `fixture: ${boxes.length} boxes, ${trees.length} trees, ${nodes.length} nodes, ${edges.length} edges; coolest saves ${coolest.stats.sun_saved_s.toFixed(0)} s`,
);
