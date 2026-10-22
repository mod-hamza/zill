// Camera rigs are PURE functions (t, params) -> RigState (PRD 13.2). No timers, no globals.
export type V3 = [number, number, number];

export type RigState = {
  position: V3;
  target: V3;
  /** vertical field of view in degrees */
  fov: number;
  /** roll in radians around the view axis (FlyRig banking) */
  roll: number;
};

export const clamp01 = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : t);
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const lerp3 = (a: V3, b: V3, t: number): V3 => [
  lerp(a[0], b[0], t),
  lerp(a[1], b[1], t),
  lerp(a[2], b[2], t),
];

/** GSAP-style power2.inOut */
export function power2InOut(t: number): number {
  const x = clamp01(t);
  return x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2;
}

/** cubic-bezier(0.22, 0.61, 0.36, 1) — the PRD default UI ease, solved numerically. */
export function easeDefault(t: number): number {
  const x = clamp01(t);
  const p1x = 0.22,
    p1y = 0.61,
    p2x = 0.36,
    p2y = 1;
  const bx = (s: number) =>
    3 * (1 - s) * (1 - s) * s * p1x + 3 * (1 - s) * s * s * p2x + s * s * s;
  const by = (s: number) =>
    3 * (1 - s) * (1 - s) * s * p1y + 3 * (1 - s) * s * s * p2y + s * s * s;
  let lo = 0,
    hi = 1;
  for (let i = 0; i < 30; i++) {
    const mid = (lo + hi) / 2;
    if (bx(mid) < x) lo = mid;
    else hi = mid;
  }
  return by((lo + hi) / 2);
}
