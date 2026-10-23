// Ch.10 "Does it work?" (40 s) — evidence: data sources + counts (meta.json), the test-suite
// summary (data/test_results.json), the method's limits, and the field-test card (a plan card
// until data/validation/field_test.json exists — listed in OPEN_ITEMS).
import { orbitRig } from "@/three/rigs";
import { win } from "../ease";
import type { ChapterFn } from "../types";

export const CH10_DUR = 40;

export const ch10: ChapterFn = (t, data) => {
  const s = t * CH10_DUR;
  return {
    camera: orbitRig(t, {
      target: [0, 260, 60],
      radius: 2100,
      height: 760,
      startDeg: 236,
      sweepDeg: 16,
      fov: 32,
      floatAmp: 0.1,
      seed: 12,
      durationS: CH10_DUR,
    }),
    sun: { dateKey: data.hero.date_id, minutes: 17 * 60 + 30 },
    look: 1,
    skyDim: 0.25,
    overlays: [
      { kind: "title", text: "Does it work?", opacity: win(s, 0.5, 4.5, 1, 1), size: "card" },
      { kind: "evidence", opacity: win(s, 2.5, CH10_DUR - 0.5, 1.2, 1.2), tests: data.tests, limits: "Model v1: buildings · mapped trees · covered links" },
      { kind: "fieldtest", opacity: win(s, 4, CH10_DUR - 0.5, 1.2, 1.2) },
    ],
  };
};
