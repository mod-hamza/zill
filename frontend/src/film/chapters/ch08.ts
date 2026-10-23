// Ch.8 "An agent, not a map." (60 s) — persona switch tourist -> rider -> crew (same engine,
// different goals; each scenario's routes + one real number from hero.json); then the proactive
// replan from the recorded replan_demo session (monitor phase: simulated 20-min delay, diff,
// autonomy decision, undo) and the architecture strip (agent roles + the real tool names used).
import { orbitRig } from "@/three/rigs";
import { ramp, rampIO, win } from "../ease";
import { departMinutes, frameGeo, lerpRig } from "../helpers";
import { payloadOf, timeline, totalMs } from "../replay";
import type { ChapterFn, FilmData } from "../types";

export const CH8_DUR = 60;
export const PERSONA_ORDER = ["tourist_walk", "rider_cycle", "crew_shuttle"];
export const CH8 = { p0: 1, pEach: 8, replan0: 26, replan1: 47, arch0: 47.5 } as const;

export function personaScenarios(data: FilmData) {
  return PERSONA_ORDER.map((id) => data.scenarios.find((s) => s.id === id)).filter(
    (s): s is NonNullable<typeof s> => !!s,
  );
}

export const ch08: ChapterFn = (t, data) => {
  const s = t * CH8_DUR;
  const ps = personaScenarios(data);
  const idx = Math.max(0, Math.min(ps.length - 1, Math.floor((s - CH8.p0) / CH8.pEach)));
  const sc = ps[idx] ?? data.hero;
  const geo = data.scenarioGeo[sc.id]?.coolest ?? data.heroGeo.coolest;
  const inPersonas = s < CH8.replan0 - 1;

  // replan: the hero trip on the simulated clock (depart 15:30 -> delayed departure)
  const tl = timeline(data.replays.replan_demo, ["monitor"]);
  const replan = payloadOf<{ diff?: { new?: { depart?: string } } }>(tl, "replan");
  const dep = departMinutes(data.hero.depart);
  const newDep = replan?.diff?.new?.depart ? departMinutes(replan.diff.new.depart.slice(11, 16)) : dep;
  const replanU = ramp(s, CH8.replan0, CH8.replan1);

  const hero = data.heroGeo.coolest;
  let camera;
  if (inPersonas) {
    const u = (s - CH8.p0 - idx * CH8.pEach) / CH8.pEach;
    const base = frameGeo(geo, 196 + 10 * u, 1.15, 0.9, 32);
    camera = base;
  } else {
    camera = orbitRig(replanU, {
      target: [hero.bbox.cx, 0, hero.bbox.cz],
      radius: hero.bbox.ext * 1.2,
      height: hero.bbox.ext * 0.95,
      startDeg: 160,
      sweepDeg: 25,
      fov: 32,
      floatAmp: 0.1,
      seed: 8,
      durationS: 30,
    });
    camera = lerpRig(frameGeo(geo, 206, 1.15, 0.9, 32), camera, rampIO(s, CH8.replan0 - 1, CH8.replan0 + 2));
  }

  const scenDep = departMinutes(sc.depart);
  return {
    camera,
    sun: inPersonas
      ? { dateKey: sc.date_id, minutes: scenDep }
      : { dateKey: data.hero.date_id, minutes: dep + (newDep - dep) * rampIO(s, CH8.replan0 + 4, CH8.replan0 + 12) },
    look: 1,
    routeWidth: 1.9,
    routes: {
      result: inPersonas ? sc.id : "hero",
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: 1, coolest: 1 },
      opacity: inPersonas ? win(s, CH8.p0 - 0.5, CH8.replan0 - 1, 0.6, 0.6) : 1,
    },
    overlays: [
      { kind: "title", text: "An agent, not a map.", opacity: win(s, 0.5, 4.5, 1, 1), size: "card" },
      { kind: "personas", opacity: win(s, CH8.p0 + 2, CH8.replan0 - 0.5, 1, 1), active: idx, progress: s },
      {
        kind: "feed",
        replayId: "replan_demo",
        cursorMs: totalMs(tl) * ramp(s, CH8.replan0 + 1, CH8.replan0 + 14),
        phases: ["monitor"],
        title: "Monitor · simulated clock",
        opacity: win(s, CH8.replan0, CH8.replan1, 1, 1),
      },
      { kind: "replan", opacity: win(s, CH8.replan0 + 4, CH8.replan1, 1, 1), progress: ramp(s, CH8.replan0 + 4, CH8.replan0 + 16) },
      { kind: "architecture", opacity: win(s, CH8.arch0, CH8_DUR + 1, 1, 0.01), progress: ramp(s, CH8.arch0, CH8.arch0 + 6) },
    ],
  };
};
