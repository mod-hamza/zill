// useStage: which experience owns the persistent canvas, quality tier, debug/QA flags, perf stats.
import { create } from "zustand";

export type Quality = "high" | "medium" | "low";
export type StageMode = "film" | "app";

type StageState = {
  mode: StageMode;
  quality: Quality;
  qualityForced: boolean;
  debug: boolean;
  qa: boolean;
  /** deterministic frame time (seconds) used by grain/pulses; the Film sets it, the App advances it */
  frameT: number;
  fps: number;
  frameMs: number;
  p95Ms: number;
  drawCalls: number;
  triangles: number;
  contextLost: boolean;
  shadeReady: boolean;
  downgrades: string[];
  setMode: (m: StageMode) => void;
  setQuality: (q: Quality, forced?: boolean) => void;
  setFlags: (f: Partial<Pick<StageState, "debug" | "qa">>) => void;
  setFrameT: (t: number) => void;
  setPerf: (
    p: Partial<
      Pick<StageState, "fps" | "frameMs" | "p95Ms" | "drawCalls" | "triangles">
    >,
  ) => void;
  setContextLost: (v: boolean) => void;
  setShadeReady: (v: boolean) => void;
  noteDowngrade: (s: string) => void;
};

export const useStage = create<StageState>((set) => ({
  mode: "app",
  quality: "high",
  qualityForced: false,
  debug: false,
  qa: false,
  frameT: 0,
  fps: 0,
  frameMs: 0,
  p95Ms: 0,
  drawCalls: 0,
  triangles: 0,
  contextLost: false,
  shadeReady: false,
  downgrades: [],
  setMode: (mode) => set({ mode }),
  setQuality: (quality, forced) =>
    set((s) => ({ quality, qualityForced: forced ?? s.qualityForced })),
  setFlags: (f) => set(f),
  setFrameT: (frameT) => set({ frameT }),
  setPerf: (p) => set(p),
  setContextLost: (contextLost) => set({ contextLost }),
  setShadeReady: (shadeReady) => set({ shadeReady }),
  noteDowngrade: (s) => set((st) => ({ downgrades: [...st.downgrades, s] })),
}));
