import { describe, expect, it } from "vitest";
import { buildAgentRoutes, parseDepart } from "./applyRoutes";

const seg = (a: [number, number], b: [number, number]) => ({
  edge: 1,
  geometry: [a, b],
  latlon: [
    [25.19, 55.26],
    [25.2, 55.27],
  ],
  arrival_s: 0,
  t_s: 10,
  sun: 0.5,
  cls: "open",
});
const stats = {
  distance_m: 1000, duration_s: 600, sun_exposure_s: 300, shaded_pct: 50, covered_pct: 0, indoor_pct: 0,
  rhl: 10, added_time_s: 0, sun_saved_s: 0, sun_saved_pct: 0, rhl_saved_pct: 0,
};
const route = (label: string) => ({
  lambda: 1, label, mode: "walk", depart: "2026-07-15T15:30:00+04:00", stats,
  nodes: [7, 8, 9], edges: [1], segments: [seg([-10, -20], [30, 40])],
});

describe("buildAgentRoutes", () => {
  it("builds a RouteResponse with endpoints from the route geometry", () => {
    const b = buildAgentRoutes(
      [route("fastest"), route("balanced"), route("coolest")],
      { "route.origin": "Al Wasl Park 2", "route.dest": "Business Bay Metro Station" },
      "summer",
    )!;
    expect(b.response.coolest.label).toBe("coolest");
    expect(b.a).toMatchObject({ node: 7, x: -10, z: -20, name: "Al Wasl Park 2" });
    expect(b.b).toMatchObject({ node: 9, x: 30, z: 40, name: "Business Bay Metro Station" });
    expect(b.departMinutes).toBe(15 * 60 + 30);
    expect(b.dateIso).toBe("2026-07-15");
  });

  it("falls back when routes are missing and rejects junk", () => {
    expect(buildAgentRoutes([route("fastest")], undefined, "summer")?.response.coolest.label).toBe("fastest");
    expect(buildAgentRoutes(undefined, undefined, "summer")).toBeNull();
    expect(buildAgentRoutes([{ label: "x" }], undefined, "summer")).toBeNull();
  });

  it("parses departure strings", () => {
    expect(parseDepart("2026-07-15T15:50:00+04:00")).toEqual({ dateIso: "2026-07-15", minutes: 950 });
    expect(parseDepart("nope")).toBeNull();
  });
});
