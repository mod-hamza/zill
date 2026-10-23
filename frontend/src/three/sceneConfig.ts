// Scene constants (one place; no magic numbers in components). Colours come from design tokens.
import type { Quality } from "@/state/stage";
import type { V3 } from "./rigs";

export const SCENE = {
  near: 3,
  nearMin: 0.5,
  nearMax: 25,
  far: 40000,
  fov: 35,
  roadY: 0.06,
  linkY: 0.11,
  routeY: 0.15,
  roadLift: 1.16,
  /** building material */
  stone: "#B5A38A",
  roughness: 0.85,
  windowPitchM: 3.2,
  floorM: 3.4,
  windowLitFraction: 0.35,
  tungsten: "#FFB46B",
  aoHeightM: 6,
  /** trees */
  canopy: ["#6E7552", "#7A7D58", "#646C4D", "#828463"],
  /** shadow camera */
  shadowBoxM: 600,
  shadowDistM: 3000,
} as const;

export const TIERS: Record<
  Quality,
  {
    dpr: number;
    shadowMap: number;
    ao: boolean;
    bloom: boolean;
    msaa: number;
    shadows: boolean;
  }
> = {
  high: {
    dpr: 1.5,
    shadowMap: 4096,
    ao: true,
    bloom: true,
    msaa: 4,
    shadows: true,
  },
  medium: {
    dpr: 1,
    shadowMap: 2048,
    ao: false,
    bloom: true,
    msaa: 2,
    shadows: true,
  },
  low: {
    dpr: 0.85,
    shadowMap: 1024,
    ao: false,
    bloom: false,
    msaa: 0,
    shadows: false,
  },
};

export type CameraPreset = { position: V3; target: V3; fov: number };

/** Bearing (deg clockwise from north, camera seen from target), distance, height -> preset. */
export function presetFrom(
  target: V3,
  bearingDeg: number,
  dist: number,
  height: number,
  fov: number,
): CameraPreset {
  const b = (bearingDeg * Math.PI) / 180;
  return {
    position: [
      target[0] + Math.sin(b) * dist,
      height,
      target[2] - Math.cos(b) * dist,
    ],
    target,
    fov,
  };
}

export const CAMERA_PRESETS: Record<string, CameraPreset> = {
  // the App's opening frame: high three-quarter view of Downtown, long lens
  default: presetFrom([120, 0, 40], 212, 2600, 1250, 30),
  // low aerial over Downtown (QA)
  aerial: presetFrom([60, 60, 60], 218, 1650, 480, 32),
};

/** Opening frame for a city: Dubai keeps its authored preset (the Film relies on it); any other
 *  city is framed from its core grid (centre, extent) with the same long-lens three-quarter view. */
export function cityView(meta: {
  city_id: string;
  core_grid: { x0: number; z0: number; rows: number; cols: number; res_m: number };
}): CameraPreset {
  if (meta.city_id === "dubai_downtown") return CAMERA_PRESETS.default!;
  const g = meta.core_grid;
  const w = g.cols * g.res_m;
  const h = g.rows * g.res_m;
  const ext = Math.max(w, h);
  return presetFrom(
    [g.x0 + w / 2, 0, g.z0 + h / 2],
    CITY_VIEW.bearingDeg,
    ext * CITY_VIEW.distPerExtent,
    ext * CITY_VIEW.heightPerExtent,
    CITY_VIEW.fov,
  );
}

export const CITY_VIEW = {
  bearingDeg: 200,
  distPerExtent: 0.95,
  heightPerExtent: 0.5,
  fov: 32,
} as const;
