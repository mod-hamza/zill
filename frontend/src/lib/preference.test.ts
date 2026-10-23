import { describe, expect, it } from "vitest";
import { colors } from "@/design/tokens";
import { normaliseRoute, type Route, type RouteStats } from "./api";
import { bestColor, bestLabel, sunDelta } from "./preference";

const stats = (o: Partial<RouteStats> = {}): RouteStats => ({
  distance_m: 1000,
  duration_s: 800,
  sun_exposure_s: 400,
  shaded_pct: 50,
  covered_pct: 0,
  indoor_pct: 0,
  rhl: 0,
  added_time_s: 60,
  sun_saved_s: -120,
  sun_saved_pct: -30,
  rhl_saved_pct: 0,
  ...o,
});
const route = (label: string): Route => ({
  lambda: 3,
  label,
  mode: "walk",
  depart: "2026-01-15T10:00:00+04:00",
  stats: stats(),
  nodes: [],
  edges: [],
  segments: [],
});

describe("preference wording", () => {
  it("labels the third route by preference", () => {
    expect(bestLabel("shade")).toBe("Coolest");
    expect(bestLabel(undefined)).toBe("Coolest");
    expect(bestLabel("sun")).toBe("Sunniest");
    expect(bestColor("sun")).toBe(colors.ember);
    expect(bestColor("shade")).toBe(colors.brass);
  });
  it("reports sun gained in sun mode from the API's own fields", () => {
    const d = sunDelta("sun", stats({ sun_gained_s: 120, sun_gained_pct: 30 }));
    expect(d).toEqual({ label: "sun gained", s: 120, pct: 30 });
    // older payloads without sun_gained_* fall back to the negated saving
    expect(sunDelta("sun", stats()).s).toBe(120);
    expect(sunDelta("shade", stats({ sun_saved_s: 90 })).label).toBe("sun saved");
  });
});

describe("normaliseRoute", () => {
  it("copies sunniest into the coolest slot in sun mode", () => {
    const r = normaliseRoute({
      fastest: route("fastest"),
      balanced: route("balanced"),
      sunniest: route("sunniest"),
      best: route("sunniest"),
      preference: "sun",
      origin: { lat: 0, lon: 0 },
      dest: { lat: 0, lon: 0 },
      date_key: "winter",
    });
    expect(r.coolest.label).toBe("sunniest");
    expect(r.preference).toBe("sun");
  });
  it("keeps shade responses unchanged and defaults the preference", () => {
    const r = normaliseRoute({
      fastest: route("fastest"),
      balanced: route("balanced"),
      coolest: route("coolest"),
      origin: { lat: 0, lon: 0 },
      dest: { lat: 0, lon: 0 },
      date_key: "summer",
    });
    expect(r.coolest.label).toBe("coolest");
    expect(r.preference).toBe("shade");
  });
});
