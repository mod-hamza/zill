// Ch.1 "Dubai, 13:00." (40 s) — black -> pre-dawn blue-umber -> sunrise on the hackathon date,
// 05:40 -> 07:10 time-lapse, slow CraneRig from the south-west towards the skyline. Title *Zill*,
// then the one-liner; caption "The sun is the first thing you plan around."
import { NAME, TAGLINE } from "@/brand";
import { craneRig } from "@/three/rigs";
import { ramp, rampIO, win } from "../ease";
import type { ChapterFn } from "../types";

export const CH1_DUR = 40;

export const ch01: ChapterFn = (t) => {
  const s = t * CH1_DUR;
  const cam = craneRig(rampIO(s, 0, CH1_DUR), {
    // composition over the PRD's starting numbers: from the west, looking east into the sunrise,
    // so the Burj is back-lit and the disc breaks the horizon to its right
    from: [-3100, 80, 40],
    to: [-1750, 210, 150],
    targetFrom: [0, 300, 270],
    targetTo: [0, 330, 290],
    fov: 33,
    fovTo: 34,
    floatAmp: 0.1,
    seed: 11,
    durationS: CH1_DUR,
  });
  // time-lapse 05:40 -> 07:10 at a gentle ease so the disc lingers as it breaks the horizon
  const minutes = 5 * 60 + 40 + 90 * ramp(s, 0, CH1_DUR);
  return {
    camera: cam,
    sun: { dateKey: "hackathon", minutes },
    look: 1,
    litFrac: 0.14,
    // open from black
    fade: 1 - ramp(s, 0.2, 4.5),
    overlays: [
      {
        kind: "title",
        text: NAME,
        sub: TAGLINE,
        opacity: win(s, 7, 27, 2.4, 2),
        subOpacity: win(s, 11.5, 27, 2, 2),
        size: "hero",
      },
      {
        kind: "caption",
        text: "The sun is the first thing you plan around.",
        opacity: win(s, 29, 39.6, 1.4, 1.2),
        align: "left",
      },
    ],
  };
};
