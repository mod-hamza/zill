// Ch.11 "Any hot city." (40 s) — crane pull-back from Downtown into darkness, then a dark matte
// globe: only cities that are actually baked (/api/cities status=ready) are filled brass; the
// roadmap cities are hollow rings labelled "roadmap". Roadmap line + go-to-market lines.
import { craneRig, orbitRig, type RigState } from "@/three/rigs";
import { ramp, rampIO, win } from "../ease";
import type { ChapterFn } from "../types";

export const CH11_DUR = 40;
export const CH11 = { pull1: 14, globe0: 15.2 } as const;
/** the globe lives high above the city (camera and globe both there; the city is out of shot) */
export const GLOBE_C: [number, number, number] = [0, 22000, -9000];
export const GLOBE_R = 2200;

export const ch11: ChapterFn = (t, data) => {
  const s = t * CH11_DUR;
  let camera: RigState;
  if (s < CH11.globe0) {
    camera = craneRig(rampIO(s, 0, CH11.pull1 + 1), {
      from: [-1500, 700, 1800],
      to: [-5200, 7800, 7200],
      targetFrom: [0, 200, 0],
      targetTo: [0, 0, 0],
      fov: 32,
      fovTo: 34,
    });
  } else {
    camera = orbitRig(ramp(s, CH11.globe0, CH11_DUR), {
      target: GLOBE_C,
      radius: 11500,
      height: GLOBE_C[1] + 900,
      startDeg: 180,
      sweepDeg: 8,
      fov: 34,
    });
  }
  const globe = s >= CH11.globe0 ? 1 : 0;
  const fade = Math.max(0, 1 - Math.abs(s - (CH11.globe0 - 0.4)) / 1.1);
  return {
    camera,
    sun: { dateKey: data.hero.date_id, minutes: 17 * 60 + 40 },
    look: 1,
    skyDim: globe ? 1 : 0.25 + 0.7 * ramp(s, 4, CH11.pull1),
    blackout: globe ? 1 : 0.85 * ramp(s, 8, CH11.pull1),
    fogScale: globe ? 0 : 1,
    shadows: !globe,
    fade,
    globe: globe * ramp(s, CH11.globe0, CH11.globe0 + 2),
    overlays: [
      { kind: "title", text: "Any hot city.", opacity: win(s, 0.5, 4.5, 1, 1), size: "card" },
      { kind: "globelabels", opacity: win(s, CH11.globe0 + 1.5, CH11_DUR + 1, 1.2, 0.01) },
      { kind: "roadmap", opacity: win(s, CH11.globe0 + 3, CH11_DUR + 1, 1.2, 0.01), progress: ramp(s, CH11.globe0 + 3, CH11.globe0 + 12) },
    ],
  };
};
