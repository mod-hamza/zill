import { describe, expect, it } from "vitest";
import type { GraphJson, Route } from "./api";
import { exposureColor, hexToLinear, linearToHex } from "./color";
import { buildRibbons, CityGraph } from "./graph";
import { pointAt, progressAt, routePolyline } from "./routeGeom";
import { lightingFor } from "@/three/lighting";

describe("exposure ramp (PRD 12.3)", () => {
  it("hits the token stops exactly", () => {
    expect(linearToHex(exposureColor(0))).toBe("#22333a");
    expect(linearToHex(exposureColor(0.5))).toBe("#6f6a55");
    expect(linearToHex(exposureColor(1))).toBe("#d07a35");
  });
  it("is monotonic in lightness from shade to mid", () => {
    const l = (x: number) => {
      const c = exposureColor(x);
      return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    };
    for (let x = 0; x < 0.5; x += 0.05)
      expect(l(x + 0.05)).toBeGreaterThan(l(x));
  });
  it("round-trips hex through linear", () => {
    expect(linearToHex(hexToLinear("#C8A15A"))).toBe("#c8a15a");
  });
});

const g: GraphJson = {
  nodes: {
    x: [0, 100, 100, 0, 500],
    z: [0, 0, 100, 100, 500],
    lat: [0, 0, 0, 0, 0],
    lon: [0, 0, 0, 0, 0],
  },
  edges: {
    u: [0, 1, 2, 3],
    v: [1, 2, 3, 0],
    length_m: [100, 100, 100, 100],
    highway: ["footway", "footway", "steps", "primary"],
    cls: ["open", "open", "open", "covered"],
    walk: [true, true, true, true],
    cycle: [true, true, false, false],
    geom: [
      [0, 0, 100, 0],
      [100, 0, 100, 100],
      [100, 100, 0, 100],
      [0, 100, 0, 0],
    ],
  },
};

describe("CityGraph.nearest", () => {
  const cg = new CityGraph(g);
  it("snaps to the nearest node", () => {
    expect(cg.nearest(90, 10)).toBe(1);
    expect(cg.nearest(3, 96)).toBe(3);
  });
  it("respects travel mode (node 3 touches no cycle edge)", () => {
    expect(cg.nearest(3, 96, "cycle")).not.toBe(3);
  });
  it("ignores isolated nodes and returns -1 beyond max distance", () => {
    expect(cg.nearest(500, 500, "walk", 50)).toBe(-1);
  });
});

describe("buildRibbons", () => {
  it("emits two vertices per point and continuous distance", () => {
    const r = buildRibbons([{ pts: [0, 0, 10, 0, 10, 10], width: 2 }], 0.1);
    expect(r.center.length).toBe(6 * 3);
    expect(r.index.length).toBe(2 * 6);
    expect(r.dist[4]).toBeCloseTo(20, 6);
    expect(r.center[1]).toBeCloseTo(0.1, 6);
    // straight segment: unit offset perpendicular to +x is +-z
    expect(Math.abs(r.offset[1]!)).toBeCloseTo(1, 6);
  });
});

const route: Route = {
  lambda: 3,
  label: "coolest",
  mode: "walk",
  depart: "2026-07-15T13:30:00+04:00",
  stats: {
    distance_m: 200,
    duration_s: 200,
    sun_exposure_s: 60,
    shaded_pct: 70,
    covered_pct: 0,
    indoor_pct: 0,
    rhl: 0,
    added_time_s: 0,
    sun_saved_s: 0,
    sun_saved_pct: 0,
    rhl_saved_pct: 0,
  },
  nodes: [0, 1, 2],
  edges: [0, 1],
  segments: [
    {
      edge: 0,
      geometry: [
        [0, 0],
        [100, 0],
      ],
      arrival_s: 0,
      t_s: 100,
      sun: 0.6,
      cls: "open",
    },
    {
      edge: 1,
      geometry: [
        [100, 0],
        [100, 100],
      ],
      arrival_s: 100,
      t_s: 100,
      sun: 0,
      cls: "indoor",
    },
  ],
};

describe("routeGeom", () => {
  it("merges shared joints and measures length", () => {
    const p = routePolyline(route);
    expect(p.pts.length / 2).toBe(3);
    expect(p.length).toBeCloseTo(200, 6);
    expect(pointAt(p, 150)).toMatchObject({ x: 100, z: 50 });
  });
  it("progress uses the route's own segment timings", () => {
    const half = progressAt(route, 0.5);
    expect(half.sunS).toBeCloseTo(60, 6);
    expect(half.shadePct).toBeCloseTo(40, 6);
    const end = progressAt(route, 1);
    expect(end.sunS).toBeCloseTo(60, 6);
    expect(end.cls).toBe("indoor");
    expect(progressAt(route, 0.25).cls).toBe("open");
  });
});

describe("lighting model", () => {
  it("is deterministic and darkens at night with lit windows", () => {
    expect(lightingFor(30, 240)).toEqual(lightingFor(30, 240));
    const night = lightingFor(-12, 260);
    const noon = lightingFor(70, 180);
    expect(night.sunIntensity).toBe(0);
    expect(night.dusk).toBeGreaterThan(0.9);
    expect(noon.dusk).toBe(0);
    expect(noon.groundSun[0]).toBeGreaterThan(noon.groundShade[0]);
  });
});
