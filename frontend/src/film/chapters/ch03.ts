// Ch.3 "Shade moves." (55 s) — TimeRig high three-quarter view of Downtown; the hero date's sun
// time-lapses 06:00 -> 19:00 over ~35 s (blended baked rasters), a brass hairline sun-path arc,
// marks at 12:00 and 16:00, then an eased return to 16:00 and a hold.
import { orbitRig } from "@/three/rigs";
import { ramp, rampIO, win } from "../ease";
import type { ChapterFn } from "../types";

export const CH3_DUR = 55;
export const CH3_SWEEP = { from: 6 * 60, to: 19 * 60, s0: 4, s1: 39 } as const;
export const CH3_HOLD = 16 * 60;

export function ch3Minutes(s: number): number {
  const { from, to, s0, s1 } = CH3_SWEEP;
  if (s <= s1) return from + (to - from) * ramp(s, s0, s1);
  return to + (CH3_HOLD - to) * rampIO(s, s1 + 0.5, s1 + 5.5);
}

export const ch03: ChapterFn = (t, data) => {
  const s = t * CH3_DUR;
  const m = ch3Minutes(s);
  const camera = orbitRig(t, {
    target: [40, 230, 140],
    radius: 2350,
    height: 1150,
    startDeg: 196,
    sweepDeg: 8,
    fov: 36,
    floatAmp: 0.1,
    seed: 3,
    durationS: CH3_DUR,
    ease: true,
  });
  const passed12 = ramp(m, 11.9 * 60, 12.1 * 60);
  const passed16 = ramp(m, 15.9 * 60, 16.1 * 60);
  return {
    camera,
    sun: { dateKey: data.hero.date_id, minutes: m },
    look: 1,
    sunArc: win(s, 2, CH3_DUR + 1, 2.5, 0.01),
    overlays: [
      { kind: "title", text: "Shade moves.", opacity: win(s, 1, 5.5, 1, 1), size: "card" },
      {
        kind: "arclabels",
        opacity: win(s, 3, CH3_DUR + 1, 2, 0.01),
        marks: [
          { hhmm: "12:00", opacity: s > CH3_SWEEP.s0 ? passed12 : 0 },
          { hhmm: "16:00", opacity: s > CH3_SWEEP.s0 ? passed16 : 0 },
        ],
      },
      {
        kind: "caption",
        text: "A shade map is only true for one minute.",
        opacity: win(s, 41, 54.5, 1.4, 1.2),
      },
    ],
  };
};
