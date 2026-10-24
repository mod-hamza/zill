// "Safe and cheap to run." (42 s design) — the mentors' questions on security, privacy and cost,
// answered from the committed docs only (film-data/facts.json <- docs/SECURITY.md, docs/COSTS.md).
// Dusk over Downtown (lit windows), a slow dolly; first privacy by design + controls, then what it
// costs to run and how many users one server handles. Unverified prices stay [TEAM TO FILL].
import { dollyRig } from "@/three/rigs";
import { sunTimesMinutes } from "@/lib/sun";
import { ramp, win } from "../ease";
import type { ChapterFn } from "../types";

export const SAFE_DUR = 42;
export const SAFE = { privacy: [3.5, 21.5], costs: 22 } as const;

export const safety: ChapterFn = (t, data) => {
  const s = t * SAFE_DUR;
  const iso = data.meta.dates[data.hero.date_id] ?? data.hero.date_id;
  const sunset = sunTimesMinutes(iso, data.meta.origin.lat, data.meta.origin.lon).sunset;
  return {
    camera: dollyRig(t, {
      from: [1650, 520, 1900],
      to: [1350, 470, 1650],
      targetFrom: [-150, 180, -60],
      targetTo: [-120, 190, -40],
      fov: 33,
      fovTo: 32,
      floatAmp: 0.1,
      seed: 16,
      durationS: SAFE_DUR,
    }),
    // just after sunset: blue-umber dusk, windows lit (the panels need a calm background)
    sun: { dateKey: data.hero.date_id, minutes: sunset + 11 },
    look: 1,
    litFrac: 0.22,
    skyDim: 0.15,
    overlays: [
      { kind: "title", text: "Safe and cheap to run.", opacity: win(s, 0.5, 4.5, 1, 1), size: "card" },
      { kind: "privacy", opacity: win(s, SAFE.privacy[0], SAFE.privacy[1], 1.2, 0.8), progress: ramp(s, SAFE.privacy[0], SAFE.privacy[0] + 6) },
      { kind: "costs", opacity: win(s, SAFE.costs, SAFE_DUR + 1, 1.2, 0.01), progress: ramp(s, SAFE.costs, SAFE.costs + 6) },
    ],
  };
};
