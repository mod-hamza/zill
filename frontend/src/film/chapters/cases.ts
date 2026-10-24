// Short cut "Case studies." (135 s) — the case studies of data/scenarios/case_studies.json
// (zill.routing.case_studies: a fixed, documented search; nothing hand-tuned), one vignette each in
// the real 3D city: the engine's fastest route (slate) and its best route for the case's preference
// (shade: brass, sun: ember), drawn from /api/route at load for the same trip and minute, two
// travellers on one clock, and a panel with ONE headline number read verbatim from the JSON.
// Dubai cases first, then Oslo (one city switch, veiled by the overlay's load gate).
import { colors } from "@/design/tokens";
import { orbitRig, type RigState } from "@/three/rigs";
import { ramp, rampIO, rampUI, win } from "../ease";
import { departMinutes, travel } from "../helpers";
import type { CaseStudy, ChapterFn, ChapterOut, FilmData, RouteGeo } from "../types";

export const CASES_DUR = 135;
/** title card, then equal slots per case */
export const CASES = { intro: 4.5, dip: 0.7 } as const;

export function caseSlots(n: number) {
  const L = n ? (CASES_DUR - CASES.intro) / n : 0;
  return { L, at: (i: number) => CASES.intro + i * L };
}

function pairBox(a: RouteGeo, b: RouteGeo) {
  const x0 = Math.min(a.bbox.x0, b.bbox.x0);
  const x1 = Math.max(a.bbox.x1, b.bbox.x1);
  const z0 = Math.min(a.bbox.z0, b.bbox.z0);
  const z1 = Math.max(a.bbox.z1, b.bbox.z1);
  return { cx: (x0 + x1) / 2, cz: (z0 + z1) / 2, ext: Math.max(x1 - x0, z1 - z0, 300) };
}

/** high three-quarter orbit over the pair; Dubai needs height (300 m towers), Oslo is low-rise */
function caseCam(cs: CaseStudy, g: { fastest: RouteGeo; coolest: RouteGeo }, u: number, L: number, i: number): RigState {
  const box = pairBox(g.fastest, g.coolest);
  const dubai = cs.c.city === "dubai_downtown";
  return orbitRig(u, {
    target: [box.cx, 0, box.cz],
    // Dubai: steep enough that the towers do not hide the streets
    radius: Math.max(dubai ? 850 : 700, box.ext * (dubai ? 1.0 : 1.1)),
    height: Math.max(dubai ? 1500 : 800, box.ext * (dubai ? 1.85 : 1.15)),
    startDeg: [196, 210, 188, 204, 220][i % 5]!,
    sweepDeg: 10,
    fov: 32,
    floatAmp: 0.1,
    seed: 30 + i,
    durationS: L,
    ease: true,
  });
}

export const bestColor = (cs: CaseStudy) => (cs.c.preference === "sun" ? colors.ember : colors.brass);

export const cases: ChapterFn = (t, data: FilmData) => {
  const s = t * CASES_DUR;
  const list = data.cases;
  const out: ChapterOut = {
    look: 1,
    routeWidth: 2.8,
    overlays: [{ kind: "title", text: "Case studies.", opacity: win(s, 0.4, CASES.intro + 0.4, 1, 1), size: "card" }],
  };
  if (!list.length) {
    out.overlays!.push({
      kind: "honest",
      text: "Case studies unavailable (data/scenarios/case_studies.json not found).",
      opacity: win(s, CASES.intro, CASES_DUR + 1, 1, 0.01),
    });
    return out;
  }
  const { L, at } = caseSlots(list.length);
  const i = Math.max(0, Math.min(list.length - 1, Math.floor((s - CASES.intro) / L)));
  const cs = list[i]!;
  const u = s - at(i); // slot-local seconds (negative during the intro)
  const dep = departMinutes(cs.c.depart);
  out.city = cs.c.city;
  out.sun = { dateKey: cs.c.date_id, minutes: dep };
  const g = cs.routeKey ? data.scenarioGeo[cs.routeKey] : undefined;
  if (g) {
    out.camera = caseCam(cs, g, ramp(u, 0, L), L, i);
    out.routes = {
      result: cs.routeKey,
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: rampUI(u, 0.6, 3), coolest: rampUI(u, 1.6, 4.4) },
      opacity: win(u, 0.2, L + 0.01, 0.5, 0.5),
    };
    // two travellers leave together; the sun clock time-lapses the longer trip
    const durA = g.fastest.route.stats.duration_s;
    const durB = g.coolest.route.stats.duration_s;
    const w0 = 5;
    const w1 = Math.max(w0 + 4, L - 3.5);
    const T = Math.max(durA, durB) * rampIO(u, w0, w1);
    if (u >= w0 - 0.5)
      out.travellers = [
        { key: "fastest", scenario: cs.routeKey!, at: travel(g.fastest, Math.min(1, T / durA)).at, color: colors.slate },
        { key: "coolest", scenario: cs.routeKey!, at: travel(g.coolest, Math.min(1, T / durB)).at, color: bestColor(cs) },
      ];
    out.sun = { dateKey: cs.c.date_id, minutes: dep + T / 60 };
  }
  // ink dips between vignettes (cuts); the intro's dip comes from the master timeline
  const cuts = list.slice(1).map((_, k) => at(k + 1));
  out.fade = rampIO(Math.max(0, ...cuts.map((c) => 1 - Math.abs(s - c) / CASES.dip)), 0, 1);
  out.overlays!.push({
    kind: "casestudy",
    index: i,
    opacity: s < CASES.intro ? 0 : win(u, 0.9, L, 0.8, 0.6),
    progress: ramp(u, 1.2, 7),
  });
  return out;
};
