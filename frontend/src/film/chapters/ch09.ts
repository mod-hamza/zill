// "Who pays." (56 s; was Ch.9 "Who it's for.") — three vignettes in the real city, each with a small UI mock and
// one number from the engine: hotel concierge (3 coolest walks from a named hotel, /api/route at
// the hero date/time), delivery rider (rider_cycle scenario, per trip), outdoor crew (crew_shuttle
// + the midday-break policy pack, labelled "verify"); then the PRD 1.3 revenue table with
// market-size placeholders, expanded to PIVOT_PLAN 4 + 8 (municipalities, schools, elderly care,
// events, well-being), then the pricing model: freemium, no ads, B2B subscriptions.
import { presetFrom } from "@/three/sceneConfig";
import { orbitRig, type RigState } from "@/three/rigs";
import { ramp, rampIO, win } from "../ease";
import { departMinutes, frameGeo, lerpRig } from "../helpers";
import type { ChapterFn, FilmData } from "../types";

export const CH9_DUR = 56;
export const CH9 = { hotel: [1.5, 12.5], fleet: [12.5, 23.5], crew: [23.5, 34.5], rev: 34.5, price: 41 } as const;

function hotelPose(data: FilmData, u: number): RigState {
  const w = data.hotelWalks[0]?.route.segments[0]?.geometry[0];
  const [x, z] = w ?? [0, 0];
  return orbitRig(u, { target: [x, 40, z], radius: 620, height: 330, startDeg: 200, sweepDeg: 18, fov: 32, floatAmp: 0.1, seed: 9, durationS: 15 });
}

export const ch09: ChapterFn = (t, data) => {
  const s = t * CH9_DUR;
  const rider = data.scenarioGeo.rider_cycle?.coolest;
  const crew = data.scenarioGeo.crew_shuttle?.coolest;
  let camera: RigState;
  let result: string | null = null;
  let minutes = departMinutes(data.hero.depart);
  if (s < CH9.hotel[1]) camera = hotelPose(data, ramp(s, 0, CH9.hotel[1]));
  else if (s < CH9.fleet[1] && rider) {
    camera = lerpRig(frameGeo(rider, 190, 1.2, 0.9, 32), frameGeo(rider, 205, 1.1, 0.85, 32), ramp(s, CH9.fleet[0], CH9.fleet[1]));
    result = "rider_cycle";
    minutes = departMinutes(data.scenarios.find((x) => x.id === "rider_cycle")?.depart ?? data.hero.depart);
  } else if (s < CH9.crew[1] && crew) {
    camera = lerpRig(frameGeo(crew, 200, 1.6, 0.95, 32), frameGeo(crew, 214, 1.45, 0.9, 32), ramp(s, CH9.crew[0], CH9.crew[1]));
    result = "crew_shuttle";
    minutes = departMinutes(data.scenarios.find((x) => x.id === "crew_shuttle")?.depart ?? data.hero.depart);
  } else {
    const p = presetFrom([0, 200, 100], 215, 2600, 1100, 30);
    camera = orbitRig(ramp(s, CH9.rev, CH9_DUR), { target: p.target, radius: 2600, height: 1100, startDeg: 215, sweepDeg: 10, fov: 30, floatAmp: 0.1, seed: 10, durationS: 16 });
  }
  // short ink dips between vignettes (cuts)
  const cuts = [CH9.hotel[1], CH9.fleet[1], CH9.crew[1]];
  const fade = Math.max(0, ...cuts.map((c) => 1 - Math.abs(s - c) / 0.7));
  return {
    camera,
    sun: { dateKey: data.hero.date_id, minutes },
    look: 1,
    fade: rampIO(fade, 0, 1),
    routeWidth: 1.9,
    routes: { result, view: "presentation", selected: "coolest", reveal: { fastest: 1, coolest: 1 }, opacity: 1 },
    overlays: [
      { kind: "title", text: "Who pays.", opacity: win(s, 0.5, 4.5, 1, 1), size: "card" },
      { kind: "vignette", which: "hotel", opacity: win(s, CH9.hotel[0] + 1.5, CH9.hotel[1], 1, 0.6), progress: ramp(s, CH9.hotel[0] + 1.5, CH9.hotel[0] + 6) },
      { kind: "vignette", which: "fleet", opacity: win(s, CH9.fleet[0] + 0.6, CH9.fleet[1], 1, 0.6), progress: ramp(s, CH9.fleet[0], CH9.fleet[0] + 5) },
      { kind: "vignette", which: "crew", opacity: win(s, CH9.crew[0] + 0.6, CH9.crew[1], 1, 0.6), progress: ramp(s, CH9.crew[0], CH9.crew[0] + 6) },
      { kind: "revenue", opacity: win(s, CH9.rev + 0.6, CH9_DUR + 1, 1.2, 0.01), progress: ramp(s, CH9.rev + 0.6, CH9.rev + 6) },
      { kind: "pricing", opacity: win(s, CH9.price, CH9_DUR + 1, 1.2, 0.01) },
    ],
  };
};
