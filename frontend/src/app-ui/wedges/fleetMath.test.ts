import { describe, expect, it } from "vitest";
import type { Route, RouteResponse } from "@/lib/api";
import { fleetTotals } from "./fleetMath";
import { rampCss } from "./ramp";

const route = (sun: number, rhl: number, dist: number, dur: number) =>
  ({
    lambda: 0,
    label: "x",
    mode: "cycle",
    depart: "",
    nodes: [],
    edges: [],
    segments: [],
    stats: { distance_m: dist, duration_s: dur, sun_exposure_s: sun, shaded_pct: 0, covered_pct: 0, indoor_pct: 0, rhl, added_time_s: 0, sun_saved_s: 0, sun_saved_pct: 0, rhl_saved_pct: 0 },
  }) as Route;
const res = (f: Route, c: Route) => ({ fastest: f, balanced: c, coolest: c, origin: { lat: 0, lon: 0 }, dest: { lat: 0, lon: 0 }, date_key: "summer" }) as RouteResponse;

describe("fleetTotals", () => {
  it("sums coolest vs fastest across riders and skips failures", () => {
    const t = fleetTotals([
      { res: res(route(600, 100, 1000, 300), route(300, 80, 1100, 330)) },
      { res: res(route(200, 50, 500, 100), route(200, 50, 500, 100)) },
      { res: null },
    ]);
    expect(t.ok).toBe(2);
    expect(t.sunSavedS).toBe(300);
    expect(t.rhlSaved).toBe(20);
    expect(t.rhlBase).toBe(150);
    expect(t.extraDistanceM).toBe(100);
    expect(t.extraTimeS).toBe(30);
  });
});

describe("rampCss", () => {
  it("clamps and interpolates the brand ramp", () => {
    expect(rampCss(-1)).toBe("rgb(34,51,58)");
    expect(rampCss(1)).toBe("rgb(208,122,53)");
    expect(rampCss(0.5)).toBe("rgb(111,106,85)");
  });
});
