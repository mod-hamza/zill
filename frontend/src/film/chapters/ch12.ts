// Ch.12 "The ask." (35 s) — golden hour on the Burj on the hero date, sun low, long shadows. The
// closing line, the team in small caps, a quiet "Try it live (A)". Holds; no cut to black.
import { NAME } from "@/brand";
import { dollyRig } from "@/three/rigs";
import { win } from "../ease";
import { sunTimesMinutes } from "@/lib/sun";
import type { ChapterFn } from "../types";

export const CH12_DUR = 35;
export const TEAM = "Abhamzay: Mohammed Hamza Ansari · Abhay Preethan";

export function closingLine() {
  return `${NAME}: the agent that routes you through the shade.`;
}

export const ch12: ChapterFn = (t, data) => {
  const s = t * CH12_DUR;
  // golden hour on the hero date: 45 -> 35 min before the computed sunset
  const iso = data.meta.dates[data.hero.date_id] ?? data.hero.date_id;
  const sunset = sunTimesMinutes(iso, data.meta.origin.lat, data.meta.origin.lon).sunset;
  return {
    camera: dollyRig(t, {
      from: [-2350, 330, 760],
      to: [-2050, 350, 640],
      targetFrom: [0, 430, 0],
      targetTo: [0, 450, 0],
      fov: 33,
      fovTo: 32,
      floatAmp: 0.1,
      seed: 13,
      durationS: CH12_DUR,
    }),
    sun: { dateKey: data.hero.date_id, minutes: sunset - 45 + 10 * t },
    look: 1,
    litFrac: 0.12,
    overlays: [
      { kind: "closing", opacity: win(s, 3, CH12_DUR + 1, 2, 0.01), teamOpacity: win(s, 8, CH12_DUR + 1, 2, 0.01), tryOpacity: win(s, 13, CH12_DUR + 1, 2, 0.01) },
    ],
  };
};
