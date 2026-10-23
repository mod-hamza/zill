// Fleet aggregation: plain sums of the API's per-route stats (coolest vs fastest).
import type { RouteResponse } from "@/lib/api";

export type FleetTotals = {
  ok: number;
  sunSavedS: number;
  rhlSaved: number;
  rhlBase: number;
  extraDistanceM: number;
  extraTimeS: number;
};

export function fleetTotals(riders: { res: RouteResponse | null }[]): FleetTotals {
  const t: FleetTotals = { ok: 0, sunSavedS: 0, rhlSaved: 0, rhlBase: 0, extraDistanceM: 0, extraTimeS: 0 };
  for (const r of riders) {
    if (!r.res) continue;
    const f = r.res.fastest.stats;
    const c = r.res.coolest.stats;
    t.ok += 1;
    t.sunSavedS += f.sun_exposure_s - c.sun_exposure_s;
    t.rhlSaved += f.rhl - c.rhl;
    t.rhlBase += f.rhl;
    t.extraDistanceM += c.distance_m - f.distance_m;
    t.extraTimeS += c.duration_s - f.duration_s;
  }
  return t;
}

