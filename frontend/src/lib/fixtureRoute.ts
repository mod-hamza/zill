// Dev-fixture stand-in for POST /api/route: returns the synthetic fixture's precomputed routes.
// Only reachable with ?fixture=1; the UI labels everything "Synthetic fixture".
import type { RouteResponse, ScenariosJson } from "./api";

export async function fixtureRoute(_body: unknown): Promise<RouteResponse> {
  void _body;
  const r = await fetch("/dev-fixture/hero.json");
  const j = (await r.json()) as ScenariosJson;
  const s = j.scenarios[0];
  if (!s) throw new Error("fixture has no scenario");
  return {
    fastest: s.fastest,
    balanced: s.balanced,
    coolest: s.coolest,
    origin: s.origin,
    dest: s.dest,
    date_key: s.date_id,
  };
}
