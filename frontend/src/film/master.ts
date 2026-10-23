// The Film's master timeline (PRD 14.1, CONTRACTS 8). CHAPTERS sum to 780 s (13:00).
// evaluate(globalSeconds, data) -> FrameState is PURE: same input, same frame — scrubbing forward or
// backward always renders the same image. Blends between chapters (continuous camera moves,
// cross-grades >= 1.5 s, ink dips across cuts) are handled here, not in the chapters.
import { lerp, smooth } from "./ease";
import { lerpRig } from "./helpers";
import type { ChapterDef, FilmData, FrameState } from "./types";
import { ch01 } from "./chapters/ch01";
import { ch02 } from "./chapters/ch02";
import { ch03 } from "./chapters/ch03";
import { ch04 } from "./chapters/ch04";
import { ch05 } from "./chapters/ch05";
import { ch06 } from "./chapters/ch06";
import { ch07 } from "./chapters/ch07";
import { ch08 } from "./chapters/ch08";
import { ch09 } from "./chapters/ch09";
import { ch10 } from "./chapters/ch10";
import { ch11 } from "./chapters/ch11";
import { ch12 } from "./chapters/ch12";

export const CHAPTERS: ChapterDef[] = [
  { id: "ch01", title: "Dubai, 13:00.", dur_s: 40, fn: ch01 },
  { id: "ch02", title: "The problem.", dur_s: 50, fn: ch02, dipIn: 2.4 },
  { id: "ch03", title: "Shade moves.", dur_s: 55, fn: ch03, dipIn: 2.4 },
  { id: "ch04", title: "A city, built in seconds.", dur_s: 90, fn: ch04, dipIn: 2.6 },
  { id: "ch05", title: "The shade engine.", dur_s: 90, fn: ch05, blendIn: 0 },
  { id: "ch06", title: "The route.", dur_s: 150, fn: ch06, blendIn: 4 },
  { id: "ch07", title: "Leave later.", dur_s: 70, fn: ch07, dipIn: 2.2 },
  { id: "ch08", title: "An agent, not a map.", dur_s: 60, fn: ch08, blendIn: 3 },
  { id: "ch09", title: "Who it's for.", dur_s: 60, fn: ch09, blendIn: 3 },
  { id: "ch10", title: "Does it work?", dur_s: 40, fn: ch10, blendIn: 3 },
  { id: "ch11", title: "Any hot city.", dur_s: 40, fn: ch11, blendIn: 3 },
  { id: "ch12", title: "The ask.", dur_s: 35, fn: ch12, dipIn: 2.4 },
];

export const TOTAL_S = CHAPTERS.reduce((a, c) => a + c.dur_s, 0);

export const CHAPTER_STARTS: number[] = CHAPTERS.reduce<number[]>((acc, c, i) => {
  acc.push(i === 0 ? 0 : acc[i - 1]! + CHAPTERS[i - 1]!.dur_s);
  return acc;
}, []);

export function chapterAt(t: number): number {
  const x = Math.max(0, Math.min(TOTAL_S - 1e-6, t));
  let i = 0;
  while (i < CHAPTERS.length - 1 && CHAPTER_STARTS[i + 1]! <= x) i++;
  return i;
}

export function defaults(t = 0): FrameState {
  return {
    t,
    chapter: 0,
    localT: 0,
    localS: 0,
    camera: { position: [-2400, 300, 3000], target: [0, 200, 0], fov: 32, roll: 0 },
    sun: { dateKey: "hackathon", minutes: 12 * 60 },
    look: 1,
    fade: 0,
    indoor: 0,
    blackout: 0,
    skyDim: 0,
    fogScale: 1,
    shadows: true,
    build: { grid: 0, roads: 0, revealR: 1e9, treeR: 1e9, links: 1, linkHighlight: 0, linkPx: 1.1 },
    litFrac: null,
    routes: {
      result: null,
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: 1, coolest: 1 },
      opacity: 1,
    },
    routeWidth: 1,
    travellers: [],
    split: null,
    shimmer: 0,
    sunArc: 0,
    sunRays: 0,
    globe: 0,
    overlays: [],
  };
}

function raw(i: number, localT: number, data: FilmData, t: number): FrameState {
  const c = CHAPTERS[i]!;
  const lt = Math.max(0, Math.min(1, localT));
  const base = defaults(t);
  const part = c.fn(lt, data);
  return {
    ...base,
    ...part,
    build: { ...base.build, ...(part.build ?? {}) },
    routes: { ...base.routes, ...(part.routes ?? {}) },
    chapter: i,
    localT: lt,
    localS: lt * c.dur_s,
    t,
  };
}

/** PURE: global seconds (+ the loaded data) -> the complete frame description. */
export function evaluate(globalSeconds: number, data: FilmData): FrameState {
  const t = Math.max(0, Math.min(TOTAL_S, globalSeconds));
  const i = chapterAt(t);
  const c = CHAPTERS[i]!;
  const start = CHAPTER_STARTS[i]!;
  const localS = t - start;
  const f = raw(i, localS / c.dur_s, data, t);

  // continuous camera / sun blend out of the previous chapter's last frame
  if (i > 0 && c.blendIn && localS < c.blendIn) {
    const prev = raw(i - 1, 1, data, t);
    const u = smooth(localS / c.blendIn);
    f.camera = lerpRig(prev.camera, f.camera, u);
    if (prev.sun.dateKey === f.sun.dateKey)
      f.sun = { dateKey: f.sun.dateKey, minutes: lerp(prev.sun.minutes, f.sun.minutes, u) };
    f.look = lerp(prev.look, f.look, u);
    f.skyDim = lerp(prev.skyDim, f.skyDim, u);
    f.blackout = lerp(prev.blackout, f.blackout, u);
  }
  // ink dips across cuts (half before, half after the boundary)
  let dip = 0;
  if (c.dipIn && localS < c.dipIn / 2) dip = 1 - localS / (c.dipIn / 2);
  const next = CHAPTERS[i + 1];
  if (next?.dipIn) {
    const toEnd = start + c.dur_s - t;
    if (toEnd < next.dipIn / 2) dip = Math.max(dip, 1 - toEnd / (next.dipIn / 2));
  }
  f.fade = Math.max(f.fade, smooth(dip));
  return f;
}
