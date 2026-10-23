// Turns agent proposal / replan route payloads into the scene's RouteResponse + A/B endpoints.
// Pure: no store access (the store calls this), so it is unit-tested.
import type { Place, Route, RouteResponse } from "@/lib/api";
import type { Endpoint } from "@/state/route";

export type AgentRoutes = {
  response: RouteResponse;
  a: Endpoint;
  b: Endpoint;
  departMinutes: number | null;
  dateIso: string | null;
};

function isRoute(v: unknown): v is Route {
  if (!v || typeof v !== "object") return false;
  const r = v as Partial<Route>;
  return typeof r.label === "string" && !!r.stats && Array.isArray(r.segments);
}

/** "2026-07-15T15:30:00+04:00" -> { dateIso, minutes } (wall-clock in the string, as the backend wrote it). */
export function parseDepart(iso: string | undefined): { dateIso: string; minutes: number } | null {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/.exec(iso ?? "");
  if (!m) return null;
  return { dateIso: m[1]!, minutes: Number(m[2]) * 60 + Number(m[3]) };
}

export function buildAgentRoutes(
  routes: unknown,
  tokens: Record<string, unknown> | undefined,
  dateKey: string,
  /** endpoint names to keep when the payload carries no tokens (replans) */
  names?: { a?: string; b?: string },
): AgentRoutes | null {
  if (!Array.isArray(routes)) return null;
  const list = routes.filter(isRoute);
  const by = (k: string) => list.find((r) => r.label === k);
  const fastest = by("fastest");
  const balanced = by("balanced") ?? fastest;
  const coolest = by("coolest") ?? balanced;
  if (!fastest || !balanced || !coolest) return null;

  const segs = coolest.segments;
  const first = segs[0];
  const last = segs[segs.length - 1];
  const g0 = first?.geometry?.[0];
  const g1 = last?.geometry?.[last.geometry.length - 1];
  const l0 = first?.latlon?.[0];
  const l1 = last?.latlon?.[last.latlon!.length - 1];
  if (!g0 || !g1 || !l0 || !l1) return null;

  const nameA = typeof tokens?.["route.origin"] === "string" ? (tokens["route.origin"] as string) : names?.a;
  const nameB = typeof tokens?.["route.dest"] === "string" ? (tokens["route.dest"] as string) : names?.b;
  const a: Endpoint = {
    node: coolest.nodes[0] ?? -1,
    x: g0[0],
    z: g0[1],
    lat: l0[0],
    lon: l0[1],
    name: nameA,
  };
  const b: Endpoint = {
    node: coolest.nodes[coolest.nodes.length - 1] ?? -1,
    x: g1[0],
    z: g1[1],
    lat: l1[0],
    lon: l1[1],
    name: nameB,
  };
  const place = (e: Endpoint): Place => ({
    name: e.name,
    lat: e.lat,
    lon: e.lon,
    node: e.node,
    x: e.x,
    z: e.z,
  });
  const dep = parseDepart(coolest.depart);
  return {
    response: {
      fastest,
      balanced,
      coolest,
      origin: place(a),
      dest: place(b),
      date_key: dateKey,
    },
    a,
    b,
    departMinutes: dep?.minutes ?? null,
    dateIso: dep?.dateIso ?? null,
  };
}
