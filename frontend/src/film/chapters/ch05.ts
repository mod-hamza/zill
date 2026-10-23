// Ch.5 "The shade engine." (90 s) — descend to a mid-height orbit; thin warm sun-ray lines from the
// true sun direction; the baked raster fades in below; zoom into one street of the hero route with
// edges coloured by exposure and three REAL per-edge labels (hero coolest segments' `sun`); the
// AC-link vignette (hero.json ac_link_story, "unverified on site"); a hairline schematic
// (sun -> shadow -> exposure -> routing); tests-passing callout (test_results.json) + limits tag.
import { presetFrom } from "@/three/sceneConfig";
import { orbitRig, type RigState } from "@/three/rigs";
import { ramp, rampIO, rampUI, win } from "../ease";
import { departMinutes, lerpRig } from "../helpers";
import type { ChapterFn, FilmData } from "../types";
import { ch4Camera } from "./ch04";

export const CH5_DUR = 90;
export const LIMITS = "Model v1: buildings · mapped trees · covered links";

const orbitPose = (u: number): RigState =>
  orbitRig(u, {
    target: [0, 170, 140],
    radius: 1250,
    height: 470,
    startDeg: 206,
    sweepDeg: 16,
    fov: 32,
    floatAmp: 0.1,
    seed: 5,
    durationS: 30,
  });

function streetPose(data: FilmData): RigState {
  const f = data.streetFocus;
  const p = presetFrom([f.x, 0, f.z], f.bearing, 260, 700, 32);
  return { ...p, roll: 0 };
}

function linkPose(data: FilmData): RigState | null {
  const a = data.acLinkArea;
  if (!a) return null;
  const d = a.ext * 0.9 + 320;
  const p = presetFrom([a.x, 0, a.z], 212, d, d * 0.8, 30);
  return { ...p, roll: 0 };
}

export const ch05: ChapterFn = (t, data) => {
  const s = t * CH5_DUR;
  const start = ch4Camera(1);
  const orbit = orbitPose(ramp(s, 0, 34));
  const street = streetPose(data);
  const link = linkPose(data) ?? street;
  let camera: RigState;
  if (s < 18) camera = lerpRig(start, orbitPose(0), rampIO(s, 0, 18));
  else if (s < 33) camera = orbitPose(ramp(s, 18, 34));
  else if (s < 62) camera = lerpRig(orbit, street, rampIO(s, 33, 43));
  else camera = lerpRig(street, link, rampIO(s, 62, 69));

  const dep = departMinutes(data.hero.depart);
  const showLink = !!data.acLink && !!data.acLinkArea;
  return {
    camera,
    sun: { dateKey: data.hero.date_id, minutes: dep },
    look: 1,
    blackout: 1 - rampUI(s, 7, 20),
    skyDim: 0.56 * (1 - rampUI(s, 0, 10)),
    sunRays: win(s, 2, 31, 3, 4),
    build: {
      grid: 0,
      roads: 0,
      revealR: 1e9,
      treeR: 1e9,
      links: 1,
      linkHighlight: showLink ? win(s, 63, 81, 2, 3) : 0,
      linkPx: 1.1 + (showLink ? 2.6 * win(s, 63, 81, 2, 3) : 0),
    },
    routeWidth: 2,
    routes: {
      result: s > 36 && s < 64 ? "hero" : null,
      view: "analysis",
      selected: "coolest",
      reveal: { fastest: rampUI(s, 38, 41), coolest: rampUI(s, 37, 41) },
      opacity: win(s, 36, 64, 1.2, 1.5),
    },
    overlays: [
      { kind: "title", text: "The shade engine.", opacity: win(s, 1, 5.5, 1, 1), size: "card" },
      { kind: "edgelabels", opacity: win(s, 44, 62, 1.5, 1.2), segs: data.labelSegs },
      { kind: "schematic", progress: rampUI(s, 61, 70), opacity: win(s, 61, 75.5, 1.2, 1.2) },
      ...(showLink && data.acLink
        ? [{ kind: "aclink" as const, opacity: win(s, 66, 80.5, 1.2, 1.2), story: data.acLink }]
        : []),
      { kind: "evidence", opacity: win(s, 77.5, CH5_DUR + 1, 1.2, 0.01), tests: data.tests, limits: LIMITS },
    ],
  };
};
