// Pure timing helpers for chapter functions (seconds are chapter-local).
import { easeDefault, power2InOut } from "@/three/rigs";

export const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** 0 before a, 1 after b, linear between. */
export function ramp(s: number, a: number, b: number): number {
  if (b <= a) return s >= b ? 1 : 0;
  return clamp01((s - a) / (b - a));
}

/** eased ramp (camera moves) */
export const rampIO = (s: number, a: number, b: number) => power2InOut(ramp(s, a, b));
/** eased ramp (UI, PRD default cubic-bezier) */
export const rampUI = (s: number, a: number, b: number) => easeDefault(ramp(s, a, b));

/** 1 inside [a, b], fading in over `fin` before... no: fades in over [a, a+fin], out over [b-fout, b]. */
export function win(s: number, a: number, b: number, fin = 0.9, fout = 0.9): number {
  if (s <= a || s >= b) return 0;
  const i = fin > 0 ? easeDefault(clamp01((s - a) / fin)) : 1;
  const o = fout > 0 ? easeDefault(clamp01((b - s) / fout)) : 1;
  return Math.min(i, o);
}

/** Deterministic typewriter: characters revealed at `cps` from `start`. */
export function typed(text: string, s: number, start: number, cps = 16): string {
  const n = Math.max(0, Math.min(text.length, Math.floor((s - start) * cps)));
  return text.slice(0, n);
}

/** caret blink as a pure function of time */
export const caretOn = (s: number) => Math.floor(s * 1.6) % 2 === 0;

export const smooth = (x: number) => {
  const t = clamp01(x);
  return t * t * (3 - 2 * t);
};
