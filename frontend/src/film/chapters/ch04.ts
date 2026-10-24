// Ch.4 "A city, built in seconds." (90 s) — black ground + hairline grid; the command bar types the
// city name; the REAL bake log (meta.build_log + shade bake_log, true counts) ticks in a slim side
// column (badge "Cached build": this replays the recorded bake, it does not re-run it); staged
// reveal: roads draw as brass hairlines -> buildings rise radially from the Burj by distance ->
// trees -> covered/AC links light in oasis; final counters from meta.json; then the pipeline
// diagram morph ("Open data in. Any hot city out.") — P2 second-city morph not built.
import { orbitRig } from "@/three/rigs";
import { ramp, rampUI, typed, caretOn, win } from "../ease";
import { departMinutes } from "../helpers";
import type { BuildLogRow, ChapterFn, FilmData } from "../types";

export const CH4_DUR = 90;
export const CH4_REVEAL_MAX_R = 2300;

export function ch4Camera(t: number) {
  return orbitRig(t, {
    target: [0, 140, 60],
    radius: 2250,
    height: 1050,
    startDeg: 222,
    sweepDeg: 34,
    fov: 31,
    heightDrift: -150,
    floatAmp: 0.1,
    seed: 4,
    durationS: CH4_DUR,
    ease: true,
  });
}

export function buildRows(data: FilmData) {
  const rows = ((data.meta.build_log ?? []) as BuildLogRow[]).map((r) => ({
    label: r.label ?? r.step,
    step: r.step,
    count: r.count,
    ms: r.dur_ms ?? undefined,
  }));
  for (const r of data.shadeBakeLog)
    rows.push({
      label: r.label ?? r.step,
      step: r.step,
      count: r.count,
      ms: r.duration_ms ?? r.dur_ms,
    });
  return rows;
}

export const ch04: ChapterFn = (t, data) => {
  const s = t * CH4_DUR;
  const name = data.meta.name;
  const rows = buildRows(data);
  // log rows appear evenly between 12 s and 62 s (the bake's real order; timings shown per row)
  const shown = Math.min(rows.length, Math.floor(ramp(s, 11, 62) * rows.length + 1e-9));
  const c = data.meta.counts;
  const cnt = (k: string) => c[k] ?? 0;
  const counterP = rampUI(s, 62, 72);
  const dep = departMinutes(data.hero.depart);
  return {
    camera: ch4Camera(t),
    sun: { dateKey: data.hero.date_id, minutes: dep },
    look: 1,
    blackout: 1,
    skyDim: 0.86 - 0.3 * ramp(s, 70, 90),
    shadows: s > 66,
    build: {
      grid: win(s, 1, 74, 3, 6) * 0.9,
      roads: rampUI(s, 14, 30),
      revealR: CH4_REVEAL_MAX_R * ramp(s, 26, 58) - 30,
      treeR: CH4_REVEAL_MAX_R * ramp(s, 52, 61),
      links: rampUI(s, 58, 63),
      linkHighlight: win(s, 58, 74, 1.5, 4),
    },
    overlays: [
      {
        kind: "command",
        text: typed(name, s, 5, 11),
        caret: s < 13 ? caretOn(s) : false,
        opacity: win(s, 3, 26, 1.2, 1.5),
        label: "Build a city",
      },
      {
        kind: "buildlog",
        rows: rows.slice(0, shown),
        opacity: win(s, 10, 70, 1.2, 1.5),
        badge: "Cached build",
      },
      {
        kind: "counters",
        opacity: win(s, 62, 78, 1.2, 1.5),
        items: [
          { label: "Buildings casting shade", value: cnt("buildings") * counterP, final: cnt("buildings") },
          { label: "Walkable edges", value: cnt("edges_walk") * counterP, final: cnt("edges_walk") },
          { label: "Trees", value: cnt("trees") * counterP, final: cnt("trees") },
          {
            label: "Covered + AC-link edges",
            value: (cnt("covered_edges") + cnt("ac_link_edges")) * counterP,
            final: cnt("covered_edges") + cnt("ac_link_edges"),
          },
        ],
      },
      {
        kind: "pipeline",
        progress: rampUI(s, 77, 85),
        opacity: win(s, 77, 90.5, 1.2, 0.01),
        line: "Open data in. Any city out.",
      },
      { kind: "title", text: "A city, built in seconds.", opacity: win(s, 1.5, 5.5, 1, 1), size: "card" },
    ],
  };
};
