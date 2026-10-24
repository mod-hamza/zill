// Short cut "Who pays." (40 s) — a slow orbit over Downtown, the segments table (pricing
// HYPOTHESES, labelled as such; company names are example target customers only; only sourced
// market figures), then the freemium line: free app, no ads, B2B subscriptions.
import { presetFrom } from "@/three/sceneConfig";
import { orbitRig } from "@/three/rigs";
import { ramp, win } from "../ease";
import { departMinutes } from "../helpers";
import type { ChapterFn } from "../types";

export const WHO_DUR = 40;
export const WHO = { table: 4, price: 17 } as const;

export const whopays: ChapterFn = (t, data) => {
  const s = t * WHO_DUR;
  const p = presetFrom([0, 200, 100], 215, 2600, 1100, 30);
  return {
    camera: orbitRig(t, { target: p.target, radius: 2600, height: 1100, startDeg: 212, sweepDeg: 12, fov: 30, floatAmp: 0.1, seed: 10, durationS: WHO_DUR }),
    sun: { dateKey: data.hero.date_id, minutes: departMinutes(data.hero.depart) },
    look: 1,
    skyDim: 0.1,
    overlays: [
      { kind: "title", text: "Who pays.", opacity: win(s, 0.4, 4, 1, 1), size: "card" },
      { kind: "revenue", opacity: win(s, WHO.table, WHO_DUR + 1, 1.2, 0.01), progress: ramp(s, WHO.table, WHO.table + 9) },
      { kind: "pricing", opacity: win(s, WHO.price, WHO_DUR + 1, 1.2, 0.01) },
    ],
  };
};
