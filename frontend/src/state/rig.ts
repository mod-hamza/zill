// useRig: what the camera is doing. The CameraDriver applies `evaluate(t)` each frame when a rig
// is active; otherwise the App's interactive controls own the camera. No timers here — whoever
// owns playback (Film master timeline, App fly-through button) writes `t`.
import { create } from "zustand";
import type { RigState, V3 } from "@/three/rigs";

export type ActiveRig = {
  id: string;
  evaluate: (t: number) => RigState;
};

type RigStore = {
  rig: ActiveRig | null;
  t: number;
  /** a one-shot camera placement for the interactive controls (QA presets, "reset view") */
  view: { position: V3; target: V3; fov: number; nonce: number } | null;
  setRig: (r: ActiveRig | null) => void;
  setT: (t: number) => void;
  setView: (v: { position: V3; target: V3; fov: number }) => void;
};

export const useRig = create<RigStore>((set) => ({
  rig: null,
  t: 0,
  view: null,
  setRig: (rig) => set({ rig, t: 0 }),
  setT: (t) => set({ t }),
  setView: (v) => set({ view: { ...v, nonce: Math.random() } }),
}));
