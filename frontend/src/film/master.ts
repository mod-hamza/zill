// The Film's master timeline (PRD 14.1, CONTRACTS 8). 15 chapters, 790 s (13:10): the pivot to
// Zill & Shams added "Two directions", "Winter in Oslo" and "Safe and cheap to run" and trimmed the
// rest. Older chapters keep their DESIGN length internally (s = t * CHn_DUR) and run uniformly a
// little faster where dur_s is shorter.
// evaluate(globalSeconds, data) -> FrameState is PURE: same input, same frame — scrubbing forward or
// backward always renders the same image. Blends between chapters (continuous camera moves,
// cross-grades >= 1.5 s, ink dips across cuts) are handled here, not in the chapters.
import { lerp, smooth } from "./ease";
import { lerpRig } from "./helpers";
import { FILM_HOME_CITY, type ChapterDef, type FilmData, type FrameState } from "./types";
import { ch01 } from "./chapters/ch01";
import { ch02 } from "./chapters/ch02";
import { ch03 } from "./chapters/ch03";
import { ch04 } from "./chapters/ch04";
import { ch05 } from "./chapters/ch05";
import { ch06 } from "./chapters/ch06";
import { ch07 } from "./chapters/ch07";
import { directions } from "./chapters/directions";
import { oslo } from "./chapters/oslo";
import { ch08 } from "./chapters/ch08";
import { ch09 } from "./chapters/ch09";
import { ch10 } from "./chapters/ch10";
import { safety } from "./chapters/safety";
import { ch11 } from "./chapters/ch11";
import { ch12 } from "./chapters/ch12";
import { cases, CASES_DUR } from "./chapters/cases";
import { whopays } from "./chapters/whopays";
import type { ChapterFn } from "./types";

/** The full 13-minute film (served at /film2). */
export const FULL_CHAPTERS: ChapterDef[] = [
  { id: "ch01", title: "Zill & Shams.", dur_s: 36, fn: ch01, notes: 1 },
  { id: "ch02", title: "The problem.", dur_s: 46, fn: ch02, dipIn: 2.4, notes: 2 },
  { id: "ch03", title: "Shade moves.", dur_s: 44, fn: ch03, dipIn: 2.4, notes: 3 },
  { id: "ch04", title: "A city, built in seconds.", dur_s: 64, fn: ch04, dipIn: 2.6, notes: 4 },
  { id: "ch05", title: "The shade engine.", dur_s: 66, fn: ch05, blendIn: 0, notes: 5 },
  { id: "ch06", title: "The route.", dur_s: 120, fn: ch06, blendIn: 4, notes: 6 },
  { id: "ch07", title: "Leave later.", dur_s: 54, fn: ch07, dipIn: 2.2, notes: 7 },
  { id: "directions", title: "Two directions.", dur_s: 50, fn: directions, dipIn: 2.4, notes: 13 },
  { id: "oslo", title: "Winter in Oslo.", dur_s: 56, fn: oslo, dipIn: 2.8, notes: 14 },
  { id: "agent", title: "An agent, not a map.", dur_s: 50, fn: ch08, dipIn: 2.8, notes: 8 },
  { id: "who", title: "Who pays.", dur_s: 56, fn: ch09, blendIn: 3, notes: 9 },
  { id: "evidence", title: "Does it work?", dur_s: 44, fn: ch10, blendIn: 3, notes: 10 },
  { id: "safety", title: "Safe and cheap to run.", dur_s: 42, fn: safety, dipIn: 2.4, notes: 15 },
  { id: "anycity", title: "Any city.", dur_s: 32, fn: ch11, blendIn: 3, notes: 11 },
  { id: "ask", title: "Try it.", dur_s: 30, fn: ch12, dipIn: 2.4, notes: 12 },
];

/**
 * Plays design seconds [from, to] of a chapter authored for `designDur` seconds as a whole chapter
 * (pure: a fixed affine map of chapter-local t). Used by the short cut to trim chapters.
 */
export function window_(fn: ChapterFn, designDur: number, from: number, to: number): ChapterFn {
  return (t, data) => fn((from + t * (to - from)) / designDur, data);
}

/** The pitch cut (served at /film), paced to docs/pitch/SCRIPT.md. */
export const SHORT_CHAPTERS: ChapterDef[] = [
  { id: "ch01", title: "Zill & Shams.", dur_s: 25, fn: window_(ch01, 40, 2, 40), notes: 1, cue: "A shade router and a sun router, from one engine." },
  { id: "ch03", title: "Shade moves.", dur_s: 30, fn: window_(ch03, 55, 0.5, 55), dipIn: 2.2, notes: 3, cue: "The core insight: a shade map is only true for one minute." },
  { id: "ch04", title: "A city, built in seconds.", dur_s: 35, fn: window_(ch04, 90, 3, 80), dipIn: 2.2, notes: 4, cue: "Open data in, a city's shade out. Cached build replay." },
  { id: "directions", title: "Two directions.", dur_s: 40, fn: directions, dipIn: 2.2, notes: 13, cue: "Same trip, same minute: shade mode and sun mode." },
  { id: "cases", title: "Case studies.", dur_s: CASES_DUR, fn: cases, dipIn: 2.2, cue: "Four customers, one number each, all from the engine." },
  { id: "agent", title: "An agent, not a map.", dur_s: 45, fn: window_(ch08, 50, 0, 50), dipIn: 2.2, notes: 8, cue: "Plans with real tools, checks its own numbers, replans, asks before acting." },
  { id: "who", title: "Who pays.", dur_s: 40, fn: whopays, dipIn: 2.2, cue: "Free for people, no ads; B2B pays. Prices are hypotheses." },
  { id: "safety", title: "Safe and cheap to run.", dur_s: 35, fn: safety, dipIn: 2.2, notes: 15, cue: "No accounts, no location stored; one small server." },
  { id: "ask", title: "Try it.", dur_s: 20, fn: window_(ch12, 35, 0, 35), dipIn: 2.2, notes: 12, cue: "Hand over to the live demo: press A." },
];

export type Cut = "short" | "full";

/** The active cut's timeline. Live bindings: setCut() swaps them before the film starts. The
 *  default is the short cut (/film); /film2 (or ?cut=full) selects the full film. */
export let CUT: Cut = "short";
export let CHAPTERS: ChapterDef[] = SHORT_CHAPTERS;
export let TOTAL_S = 0;
export let CHAPTER_STARTS: number[] = [];

function starts(list: ChapterDef[]): number[] {
  return list.reduce<number[]>((acc, c, i) => {
    acc.push(i === 0 ? 0 : acc[i - 1]! + list[i - 1]!.dur_s);
    return acc;
  }, []);
}

export function setCut(cut: Cut): void {
  CUT = cut;
  CHAPTERS = cut === "full" ? FULL_CHAPTERS : SHORT_CHAPTERS;
  TOTAL_S = CHAPTERS.reduce((a, c) => a + c.dur_s, 0);
  CHAPTER_STARTS = starts(CHAPTERS);
}
setCut("short");

/** which cut a URL asks for: ?cut= wins, else /film2 is the full film, anything else the short cut */
export function cutFor(pathname: string, search: string): Cut {
  const q = new URLSearchParams(search).get("cut");
  if (q === "full" || q === "short") return q;
  return pathname.startsWith("/film2") ? "full" : "short";
}

export function chapterAt(t: number): number {
  const x = Math.max(0, Math.min(TOTAL_S - 1e-6, t));
  let i = 0;
  while (i < CHAPTERS.length - 1 && CHAPTER_STARTS[i + 1]! <= x) i++;
  return i;
}

export function defaults(t = 0): FrameState {
  return {
    t,
    city: FILM_HOME_CITY,
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

  // continuous camera / sun blend out of the previous chapter's last frame (same city only)
  const prev = i > 0 && c.blendIn && localS < c.blendIn ? raw(i - 1, 1, data, t) : null;
  if (prev && prev.city === f.city) {
    const u = smooth(localS / c.blendIn!);
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
