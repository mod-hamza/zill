import { describe, expect, it } from "vitest";
import { to_local, to_wgs84, type Origin } from "./geo";

const O: Origin = { lat: 25.1972, lon: 55.2744 };

function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

describe("geo", () => {
  it("origin maps to (0, 0)", () => {
    const [x, z] = to_local(O.lat, O.lon, O);
    expect(Math.abs(x)).toBeLessThan(1e-9);
    expect(Math.abs(z)).toBeLessThan(1e-9);
  });

  it("north is -z and east is +x", () => {
    expect(to_local(O.lat + 0.001, O.lon, O)[1]).toBeLessThan(0);
    expect(to_local(O.lat, O.lon + 0.001, O)[0]).toBeGreaterThan(0);
  });

  it("round-trips 1000 random points to < 0.01 m", () => {
    const r = rng(42);
    for (let i = 0; i < 1000; i++) {
      const x = (r() - 0.5) * 6000;
      const z = (r() - 0.5) * 6000;
      const [lat, lon] = to_wgs84(x, z, O);
      const [x2, z2] = to_local(lat, lon, O);
      expect(Math.hypot(x2 - x, z2 - z)).toBeLessThan(0.01);
    }
  });
});
