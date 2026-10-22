import { describe, expect, it } from "vitest";
import {
  craneRig,
  dollyRig,
  easedDistance,
  flyPathFromPolyline,
  flyRig,
  floatOffset,
  FLOAT_MAX_M,
  orbitRig,
  timeRig,
  type V3,
} from "./index";

const ts = Array.from({ length: 41 }, (_, i) => i / 40);

const zigzag: V3[] = [
  [0, 4, 0],
  [60, 4, 10],
  [120, 6, -40],
  [180, 4, 30],
  [240, 8, -20],
  [300, 4, 0],
];

describe("rigs are pure and deterministic", () => {
  const rigs: [string, (t: number) => unknown][] = [
    [
      "orbit",
      (t) =>
        orbitRig(t, {
          target: [0, 100, 0],
          radius: 900,
          height: 400,
          startDeg: 200,
          sweepDeg: 40,
          floatAmp: 0.1,
          seed: 3,
        }),
    ],
    [
      "dolly",
      (t) =>
        dollyRig(t, {
          from: [0, 10, 0],
          to: [100, 20, 50],
          targetFrom: [0, 0, -100],
          floatAmp: 0.1,
        }),
    ],
    [
      "crane",
      (t) =>
        craneRig(t, {
          from: [-2400, 90, 3000],
          to: [-1100, 220, 1500],
          targetFrom: [0, 300, 0],
          targetTo: [0, 200, 0],
        }),
    ],
    [
      "time",
      (t) =>
        timeRig(t, {
          position: [-800, 600, 900],
          target: [0, 0, 0],
          floatAmp: 0.12,
          seed: 9,
        }),
    ],
    ["fly", (t) => flyRig(t, { points: zigzag, floatAmp: 0.1 })],
  ];
  for (const [name, f] of rigs) {
    it(`${name}: same t -> identical output (also out of order)`, () => {
      const a = ts.map(f);
      const b = [...ts].reverse().map(f).reverse();
      expect(JSON.stringify(a)).toBe(JSON.stringify(b));
      for (const s of a) expect(JSON.stringify(s)).not.toContain("null");
    });
  }
});

describe("FlyRig", () => {
  it("never banks more than 4 degrees, even when asked to", () => {
    for (const t of Array.from({ length: 501 }, (_, i) => i / 500)) {
      const s = flyRig(t, { points: zigzag, bankMaxDeg: 30 });
      expect(Math.abs(s.roll)).toBeLessThanOrEqual((4 * Math.PI) / 180 + 1e-9);
    }
  });
  it("starts at the first point and ends at the last", () => {
    const a = flyRig(0, { points: zigzag });
    const b = flyRig(1, { points: zigzag });
    expect(a.position[0]).toBeCloseTo(0, 3);
    expect(b.position[0]).toBeCloseTo(300, 3);
  });
  it("speed profile is eased and monotonic", () => {
    let prev = -1;
    for (const t of ts) {
      const d = easedDistance(t);
      expect(d).toBeGreaterThanOrEqual(prev);
      prev = d;
    }
    expect(easedDistance(0)).toBe(0);
    expect(easedDistance(1)).toBeCloseTo(1, 9);
    expect(easedDistance(0.02)).toBeLessThan(0.02); // slow start
  });
  it("path builder keeps endpoints", () => {
    const p = flyPathFromPolyline(
      [
        [0, 0],
        [5, 0],
        [30, 0],
        [31, 2],
      ],
      6,
    );
    expect(p[0]).toEqual([0, 6, 0]);
    expect(p[p.length - 1]).toEqual([31, 6, 2]);
  });
});

describe("float", () => {
  it("is bounded by 0.15 m and deterministic", () => {
    for (let s = 0; s < 300; s += 0.37) {
      const o = floatOffset(s, 5, 1.0);
      for (const c of o)
        expect(Math.abs(c)).toBeLessThanOrEqual(FLOAT_MAX_M + 1e-12);
      expect(floatOffset(s, 5, 1.0)).toEqual(o);
    }
  });
});
