// Ch.7 "Leave later." (70 s) — the departure optimiser's REAL table (hero.json `departure`): x =
// departure (5-min steps), y = sun exposure (min), ember area, brass recommended point; the chart
// cursor scrubs the 3D sun; the recommendation line is rendered from the data (if the optimiser
// says "leave now", the chapter says the agent checked and confirms — no invented saving); a
// scripted "Approve plan" press by t -> "Active plan" card.
import { orbitRig } from "@/three/rigs";
import { ramp, rampUI, win } from "../ease";
import { departMinutes } from "../helpers";
import type { ChapterFn } from "../types";

export const CH7_DUR = 70;
export const CH7 = { chart0: 4, cursor0: 9, cursor1: 37, rec: 38, approve: 50.5, active: 52 } as const;

export const ch07: ChapterFn = (t, data) => {
  const s = t * CH7_DUR;
  const hero = data.hero;
  const table = hero.departure?.table ?? [];
  const dep = departMinutes(hero.depart);
  const g = data.heroGeo.coolest.bbox;
  const fg = data.heroGeo.fastest.bbox;
  const cx = (Math.min(g.x0, fg.x0) + Math.max(g.x1, fg.x1)) / 2;
  const cz = (Math.min(g.z0, fg.z0) + Math.max(g.z1, fg.z1)) / 2;
  const ext = Math.max(g.ext, fg.ext);
  const camera = orbitRig(t, {
    // framed so the route sits in the right two thirds, the chart lives on the left
    target: [cx - ext * 0.22, 0, cz],
    radius: ext * 0.95,
    height: ext * 0.62,
    startDeg: 168,
    sweepDeg: 14,
    fov: 32,
    floatAmp: 0.1,
    seed: 7,
    durationS: CH7_DUR,
    ease: true,
  });
  // cursor: sweep the table, then settle on the recommended row
  const rq = hero.departure?.requested?.depart_time;
  const rc = hero.departure?.recommended?.depart_time;
  const laterHelps = !!rq && !!rc && rq !== rc;
  const recIdx = Math.max(0, table.findIndex((r) => r.recommended));
  const n = Math.max(1, table.length - 1);
  const sweep = ramp(s, CH7.cursor0, CH7.cursor1);
  const settle = rampUI(s, CH7.cursor1, CH7.rec);
  const cursor = sweep * (1 - settle) + (recIdx / n) * settle;
  const row = table.length ? cursor * n : 0;
  const i0 = Math.floor(row);
  const tA = table[Math.min(i0, table.length - 1)];
  const tB = table[Math.min(i0 + 1, table.length - 1)];
  const mA = tA ? departMinutes(tA.depart_time) : dep;
  const mB = tB ? departMinutes(tB.depart_time) : dep;
  const minutes = mA + (mB - mA) * (row - i0);
  return {
    camera,
    sun: { dateKey: hero.date_id, minutes: s < CH7.cursor0 ? dep : minutes },
    look: 1,
    routeWidth: 1.9,
    routes: {
      result: "hero",
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: 0, coolest: 1 },
      opacity: 1,
    },
    overlays: [
      { kind: "title", text: laterHelps ? "Leave later." : "Leave later?", opacity: win(s, 0.6, 4.6, 1, 1), size: "card" },
      {
        kind: "chart",
        opacity: win(s, CH7.chart0, CH7.active + 1.5, 1.2, 1),
        cursor,
        reveal: rampUI(s, CH7.chart0, CH7.chart0 + 4),
        approve: ramp(s, CH7.approve - 0.3, CH7.approve + 0.3),
        active: 0,
        rec: rampUI(s, CH7.rec, CH7.rec + 1.5),
      },
      {
        kind: "chart",
        opacity: win(s, CH7.active, CH7_DUR + 1, 1.2, 0.01),
        cursor,
        reveal: 1,
        approve: 1,
        active: 1,
        rec: 1,
      },
    ],
  };
};
