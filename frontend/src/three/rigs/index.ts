// Pure camera rigs (PRD 13.2). Every rig: (t in [0,1], params) -> RigState. Deterministic.
import { CatmullRomCurve3, Vector3 } from "three";
import { floatOffset } from "./float";
import {
  clamp01,
  lerp,
  lerp3,
  power2InOut,
  type RigState,
  type V3,
} from "./types";

export * from "./types";
export { floatOffset, FLOAT_MAX_M } from "./float";

const DEG = Math.PI / 180;
const add3 = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];

type FloatParams = { seed?: number; floatAmp?: number; durationS?: number };

function withFloat(s: RigState, t: number, p: FloatParams): RigState {
  if (!p.floatAmp) return s;
  const o = floatOffset(t * (p.durationS ?? 30), p.seed ?? 1, p.floatAmp);
  return { ...s, position: add3(s.position, o) };
}

// ---------------------------------------------------------------------------------------------
export type OrbitParams = FloatParams & {
  target: V3;
  radius: number;
  height: number;
  /** compass bearing (deg, clockwise from north) of the camera as seen from the target at t=0 */
  startDeg: number;
  sweepDeg: number;
  fov?: number;
  /** metres of altitude change over the move (positive = rises) */
  heightDrift?: number;
  ease?: boolean;
};

export function orbitRig(t: number, p: OrbitParams): RigState {
  const u = p.ease ? power2InOut(t) : clamp01(t);
  const b = (p.startDeg + p.sweepDeg * u) * DEG;
  const h = p.height + (p.heightDrift ?? 0) * u;
  const position: V3 = [
    p.target[0] + Math.sin(b) * p.radius,
    h,
    p.target[2] - Math.cos(b) * p.radius,
  ];
  return withFloat(
    { position, target: [...p.target], fov: p.fov ?? 35, roll: 0 },
    t,
    p,
  );
}

// ---------------------------------------------------------------------------------------------
export type DollyParams = FloatParams & {
  from: V3;
  to: V3;
  targetFrom: V3;
  targetTo?: V3;
  fov?: number;
  fovTo?: number;
};

export function dollyRig(t: number, p: DollyParams): RigState {
  const u = power2InOut(t);
  return withFloat(
    {
      position: lerp3(p.from, p.to, u),
      target: lerp3(p.targetFrom, p.targetTo ?? p.targetFrom, u),
      fov: lerp(p.fov ?? 35, p.fovTo ?? p.fov ?? 35, u),
      roll: 0,
    },
    t,
    p,
  );
}

// ---------------------------------------------------------------------------------------------
export type CraneParams = FloatParams & {
  from: V3;
  to: V3;
  targetFrom: V3;
  targetTo: V3;
  fov?: number;
  fovTo?: number;
};

/** Rise + tilt: horizontal travel eased in-out, the rise front-loaded (a crane arm lifts first). */
export function craneRig(t: number, p: CraneParams): RigState {
  const u = power2InOut(t);
  const rise = 1 - (1 - clamp01(t)) ** 2.2;
  const position: V3 = [
    lerp(p.from[0], p.to[0], u),
    lerp(p.from[1], p.to[1], rise),
    lerp(p.from[2], p.to[2], u),
  ];
  return withFloat(
    {
      position,
      target: lerp3(p.targetFrom, p.targetTo, u),
      fov: lerp(p.fov ?? 35, p.fovTo ?? p.fov ?? 35, u),
      roll: 0,
    },
    t,
    p,
  );
}

// ---------------------------------------------------------------------------------------------
export type TimeRigParams = FloatParams & {
  position: V3;
  target: V3;
  fov?: number;
};

/** Static camera (the sun is what moves). */
export function timeRig(t: number, p: TimeRigParams): RigState {
  return withFloat(
    {
      position: [...p.position],
      target: [...p.target],
      fov: p.fov ?? 35,
      roll: 0,
    },
    t,
    p,
  );
}

// ---------------------------------------------------------------------------------------------
export type FlyParams = FloatParams & {
  /** path points in local metres; y is the camera height at that point (author per segment) */
  points: V3[];
  /** metres ahead along the path to look at (PRD 25–40) */
  lookahead?: number;
  /** look-target height relative to the camera path (negative = look slightly down) */
  lookDrop?: number;
  /** max bank in degrees (clamped to 4) */
  bankMaxDeg?: number;
  fov?: number;
  /** fraction of the move spent accelerating (and decelerating) */
  accel?: number;
};

export const FLY_BANK_LIMIT_DEG = 4;

const curveCache = new WeakMap<
  V3[],
  { curve: CatmullRomCurve3; length: number }
>();

function curveFor(points: V3[]): { curve: CatmullRomCurve3; length: number } {
  let c = curveCache.get(points);
  if (!c) {
    const pts = points.map((p) => new Vector3(p[0], p[1], p[2]));
    if (pts.length === 1)
      pts.push(pts[0]!.clone().add(new Vector3(0.01, 0, 0)));
    const curve = new CatmullRomCurve3(pts, false, "centripetal", 0.5);
    curve.arcLengthDivisions = Math.max(200, pts.length * 20);
    c = { curve, length: curve.getLength() };
    curveCache.set(points, c);
  }
  return c;
}

/** Trapezoidal speed profile -> normalised distance in [0,1]. */
export function easedDistance(t: number, accel = 0.12): number {
  const x = clamp01(t);
  const a = Math.min(Math.max(accel, 1e-3), 0.5);
  const v = 1 / (1 - a);
  if (x < a) return (v * x * x) / (2 * a);
  if (x > 1 - a) return 1 - (v * (1 - x) ** 2) / (2 * a);
  return v * (a / 2 + (x - a));
}

function heading(v: Vector3): number {
  return Math.atan2(v.x, -v.z);
}

export function flyRig(t: number, p: FlyParams): RigState {
  const { curve, length } = curveFor(p.points);
  const look = p.lookahead ?? 32;
  const s = easedDistance(t, p.accel ?? 0.12);
  const u = clamp01(s);
  const uLook = clamp01(u + look / Math.max(length, 1e-6));
  const pos = curve.getPointAt(u);
  let tgt = curve.getPointAt(uLook);
  if (uLook - u < 1e-4) {
    // at the end of the path keep looking along the final tangent
    tgt = pos.clone().add(curve.getTangentAt(1).multiplyScalar(look));
  }
  tgt.y += p.lookDrop ?? -1.5;
  // bank from the heading change between here and the look point, clamped to <= 4 deg
  const t0 = curve.getTangentAt(u);
  const t1 = curve.getTangentAt(uLook);
  let dh = heading(t1) - heading(t0);
  while (dh > Math.PI) dh -= 2 * Math.PI;
  while (dh < -Math.PI) dh += 2 * Math.PI;
  const maxBank =
    Math.min(Math.abs(p.bankMaxDeg ?? FLY_BANK_LIMIT_DEG), FLY_BANK_LIMIT_DEG) *
    DEG;
  // fade bank in/out with speed so we never roll while stationary
  const speedFade = Math.min(1, Math.min(t, 1 - t) / 0.08);
  const roll =
    Math.max(-maxBank, Math.min(maxBank, -dh * 0.6)) * clamp01(speedFade);
  return withFloat(
    {
      position: [pos.x, pos.y, pos.z],
      target: [tgt.x, tgt.y, tgt.z],
      fov: p.fov ?? 40,
      roll,
    },
    t,
    p,
  );
}

/** Build a fly path from a route polyline (x,z pairs) at an authored camera height. */
export function flyPathFromPolyline(
  pts: [number, number][],
  height: number,
  spacing = 12,
): V3[] {
  if (pts.length === 0) return [];
  const out: V3[] = [[pts[0]![0], height, pts[0]![1]]];
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    const [x0, z0] = pts[i - 1]!;
    const [x1, z1] = pts[i]!;
    acc += Math.hypot(x1 - x0, z1 - z0);
    if (acc >= spacing || i === pts.length - 1) {
      out.push([x1, height, z1]);
      acc = 0;
    }
  }
  return out;
}
