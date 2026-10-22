// Deterministic, seeded low-frequency "float" (PRD 13.2: <= 0.15 m, handheld-free).
// Value noise on a hashed lattice; same (t, seed) -> same offset, always.
import type { V3 } from "./types";

function hash(n: number, seed: number): number {
  let h = (n * 374761393 + seed * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return ((h >>> 0) / 4294967295) * 2 - 1;
}

function noise1(x: number, seed: number): number {
  const i = Math.floor(x);
  const f = x - i;
  const u = f * f * (3 - 2 * f);
  return hash(i, seed) * (1 - u) + hash(i + 1, seed) * u;
}

export const FLOAT_MAX_M = 0.15;

/**
 * Float offset at time `seconds`. `amp` is clamped to FLOAT_MAX_M. `freq` in Hz (default 0.07).
 * Two octaves, normalised so the result never exceeds `amp` per axis.
 */
export function floatOffset(
  seconds: number,
  seed = 1,
  amp = 0.1,
  freq = 0.07,
): V3 {
  const a = Math.min(Math.abs(amp), FLOAT_MAX_M);
  const f = (axis: number) =>
    (noise1(seconds * freq, seed * 3 + axis) * 0.7 +
      noise1(seconds * freq * 2.3, seed * 7 + axis + 11) * 0.3) *
    a;
  return [f(0), f(1), f(2)];
}
