// Film playback state. `t` (global seconds) is the ONLY clock; everything else is evaluate(t).
// The single frame loop (FilmWorld, inside the canvas) advances t while autoplaying or jumping and
// publishes the evaluated frame for the DOM overlays.
import { create } from "zustand";
import { CHAPTER_STARTS, TOTAL_S } from "./master";
import type { FrameState } from "./types";

export const SPEED_MIN = 0.85;
export const SPEED_MAX = 1.15;
export const JUMP_S = 1.2;

type Jump = { from: number; to: number; elapsed: number };

type FilmStore = {
  t: number;
  playing: boolean;
  speed: number;
  /** QA-only autoplay multiplier (?qa=1&rate=20); 1 otherwise */
  rate: number;
  jump: Jump | null;
  frame: FrameState | null;
  chromeHidden: boolean;
  showElapsed: boolean;
  presenter: boolean;
  qa: boolean;
  /** set when t changed by scroll/keys so the controller does not echo it back */
  source: "scroll" | "loop" | "init";
  setT: (t: number, source?: FilmStore["source"]) => void;
  setPlaying: (p: boolean) => void;
  toggle: () => void;
  nudgeSpeed: (d: number) => void;
  jumpTo: (t: number) => void;
  jumpChapter: (i: number) => void;
  setFrame: (f: FrameState) => void;
  set: (p: Partial<FilmStore>) => void;
};

const clampT = (t: number) => Math.max(0, Math.min(TOTAL_S, t));

export const useFilm = create<FilmStore>((set, get) => ({
  t: 0,
  playing: false,
  speed: 1,
  rate: 1,
  jump: null,
  frame: null,
  chromeHidden: false,
  showElapsed: false,
  presenter: false,
  qa: false,
  source: "init",
  setT: (t, source = "scroll") => set({ t: clampT(t), source, jump: source === "scroll" ? null : get().jump }),
  setPlaying: (playing) => set({ playing, jump: playing ? null : get().jump }),
  toggle: () => set({ playing: !get().playing, jump: null }),
  nudgeSpeed: (d) =>
    set({ speed: Math.round(Math.max(SPEED_MIN, Math.min(SPEED_MAX, get().speed + d)) * 100) / 100 }),
  jumpTo: (to) => set({ jump: { from: get().t, to: clampT(to), elapsed: 0 } }),
  jumpChapter: (i) => {
    const k = Math.max(0, Math.min(CHAPTER_STARTS.length - 1, i));
    get().jumpTo(CHAPTER_STARTS[k]! + 0.01);
  },
  setFrame: (frame) => set({ frame }),
  set: (p) => set(p),
}));
