// Ch.8 "Two directions." (50 s design) — one trip at one minute, two needs. The same Dubai street
// pair from hero.json `sun` (winter): first the engine's SHADE-mode routes (fastest slate, shadiest
// oasis, from /api/route at load), then SUN mode (fastest slate, sunniest ember, the scenario
// verbatim), then both side by side (shade oasis vs sun ember) with two walkers on the same clock,
// a numbers panel and the scenario's well-being card. No number is authored here.
import { colors } from "@/design/tokens";
import { orbitRig } from "@/three/rigs";
import { ramp, rampIO, rampUI, win } from "../ease";
import { departMinutes, travel } from "../helpers";
import type { ChapterFn, ChapterOut, FilmData, RouteGeo } from "../types";

export const DIR_DUR = 50;
/** the shade-mode route's colour in this chapter: oasis reads clearly against the ember sun route
 *  (brass and ember are too close side by side) */
export const SHADE_ROUTE = colors.oasis;
export const DIR = { shade0: 4.5, sun0: 18, both0: 31.5, walk0: 33, walk1: 47 } as const;

/** union framing of every route of the pair */
function pairBox(data: FilmData) {
  const gs: RouteGeo[] = [];
  for (const k of ["dir_sun", "dir_shade"]) {
    const g = data.scenarioGeo[k];
    if (g) gs.push(g.fastest, g.coolest);
  }
  if (!gs.length) return null;
  const x0 = Math.min(...gs.map((g) => g.bbox.x0));
  const x1 = Math.max(...gs.map((g) => g.bbox.x1));
  const z0 = Math.min(...gs.map((g) => g.bbox.z0));
  const z1 = Math.max(...gs.map((g) => g.bbox.z1));
  return { cx: (x0 + x1) / 2, cz: (z0 + z1) / 2, ext: Math.max(x1 - x0, z1 - z0, 300) };
}

export const directions: ChapterFn = (t, data) => {
  const s = t * DIR_DUR;
  const d = data.directions;
  const box = pairBox(data);
  const out: ChapterOut = {
    look: 1,
    routeWidth: 2.6,
    overlays: [{ kind: "title", text: "Two directions.", opacity: win(s, 0.6, 4.6, 1, 1), size: "card" }],
  };
  if (!d || !box) {
    out.overlays!.push({
      kind: "honest",
      text: "Sun scenarios unavailable (data/scenarios/hero.json has no `sun` block).",
      opacity: win(s, 5, DIR_DUR + 1, 1, 0.01),
    });
    return out;
  }
  const sc = d.scenario;
  const dep = departMinutes(sc.depart);
  out.sun = { dateKey: sc.date_id, minutes: dep };
  out.camera = orbitRig(t, {
    // high three-quarter: Downtown's towers are ~300 m tall, so a low orbit hides the streets
    target: [box.cx + box.ext * 0.12, 0, box.cz],
    radius: Math.max(900, box.ext * 1.15),
    height: Math.max(1250, box.ext * 1.6),
    startDeg: 196,
    sweepDeg: 14,
    fov: 32,
    floatAmp: 0.1,
    seed: 14,
    durationS: DIR_DUR,
    ease: true,
  });

  const hasShade = !!data.routeSets.dir_shade;
  const shadeEnd = hasShade ? DIR.sun0 - 0.4 : 0;
  const sunEnd = DIR.both0 - 0.3;
  const draw = (a: number) => ({ fastest: rampUI(s, a, a + 2.5), coolest: rampUI(s, a + 1.2, a + 4.5) });
  if (hasShade && s < shadeEnd) {
    out.routes = { result: "dir_shade", view: "presentation", selected: "coolest", reveal: draw(DIR.shade0), opacity: win(s, DIR.shade0 - 0.5, shadeEnd, 0.5, 0.6) };
  } else if (s < sunEnd || !hasShade) {
    const a = hasShade ? DIR.sun0 : DIR.shade0;
    out.routes = {
      result: "dir_sun",
      view: "presentation",
      selected: "coolest",
      reveal: draw(a),
      opacity: win(s, a - 0.5, hasShade ? sunEnd : DIR_DUR + 1, 0.5, hasShade ? 0.6 : 0.01),
    };
  } else {
    out.routes = {
      result: "dir_both",
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: rampUI(s, DIR.both0, DIR.both0 + 2.5), coolest: rampUI(s, DIR.both0 + 0.4, DIR.both0 + 3) },
      opacity: win(s, DIR.both0 - 0.3, DIR_DUR + 1, 0.5, 0.01),
    };
    // two walkers leave together; the clock time-lapses the longer walk
    const both = data.scenarioGeo.dir_both;
    if (both) {
      const durA = both.fastest.route.stats.duration_s;
      const durB = both.coolest.route.stats.duration_s;
      const T = Math.max(durA, durB) * rampIO(s, DIR.walk0, DIR.walk1);
      out.travellers = [
        { key: "fastest", scenario: "dir_both", at: travel(both.fastest, Math.min(1, T / durA)).at, color: SHADE_ROUTE },
        { key: "coolest", scenario: "dir_both", at: travel(both.coolest, Math.min(1, T / durB)).at, color: colors.ember },
      ];
      out.sun = { dateKey: sc.date_id, minutes: dep + T / 60 };
    }
  }

  const ov = out.overlays!;
  if (hasShade)
    ov.push({ kind: "directions", phase: "shade", opacity: win(s, DIR.shade0 + 1, shadeEnd, 1, 0.6), progress: ramp(s, DIR.shade0 + 1, DIR.shade0 + 6) });
  ov.push({
    kind: "directions",
    phase: "sun",
    opacity: win(s, (hasShade ? DIR.sun0 : DIR.shade0) + 1, hasShade ? sunEnd : DIR_DUR + 1, 1, hasShade ? 0.6 : 0.01),
    progress: ramp(s, (hasShade ? DIR.sun0 : DIR.shade0) + 1, (hasShade ? DIR.sun0 : DIR.shade0) + 6),
  });
  if (hasShade)
    ov.push({ kind: "directions", phase: "both", opacity: win(s, DIR.both0 + 1, DIR_DUR + 1, 1, 0.01), progress: ramp(s, DIR.both0 + 1, DIR.both0 + 6) });
  if (sc.wellbeing) ov.push({ kind: "wellbeing", which: "directions", opacity: win(s, DIR.both0 + 4, DIR_DUR + 1, 1.2, 0.01) });
  ov.push({ kind: "caption", text: "Same trip. Same minute. Two different needs.", opacity: win(s, 6.5, 15.5, 1.2, 1.2) });
  return out;
};
