"use client";
// App-side playback owners (the Film owns these itself): frame-t, time-lapse, fly-through.
// They WRITE `t`/minutes into stores; rigs and shaders stay pure functions of those values.
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { Mesh, Raycaster, Vector3, type Object3D } from "three";
import type { Route } from "@/lib/api";
import { progressAt, routePolyline, type RoutePolyline } from "@/lib/routeGeom";
import { hhmmToMinutes } from "@/lib/sun";
import { useCity } from "@/state/city";
import { useRig } from "@/state/rig";
import { useRoute } from "@/state/route";
import { useStage } from "@/state/stage";
import { useSun } from "@/state/sun";
import { easedDistance, flyRig, type V3 } from "./rigs";

export const FLY_ACCEL = 0.12;
import { presetFrom } from "./sceneConfig";
import { setIndoorAmount } from "./useLighting";

export const FLY = {
  eyeM: 3.2,
  roofClearM: 14,
  sampleM: 10,
  speedMps: 22,
  minS: 18,
  maxS: 75,
  timelapseMinPerS: 40,
};

/** Fly path with authored heights: eye level on open ground, above roofs where the route passes
 *  under/through buildings (malls, covered links). Heights come from a downward raycast. */
export function authorFlyPath(
  poly: RoutePolyline,
  buildings: Object3D | null,
): V3[] {
  const ray = new Raycaster();
  const down = new Vector3(0, -1, 0);
  const meshes: Mesh[] = [];
  buildings?.traverse((o) => {
    if ((o as Mesh).isMesh) meshes.push(o as Mesh);
  });
  const raw: { x: number; z: number; h: number }[] = [];
  const n = Math.max(2, Math.ceil(poly.length / FLY.sampleM) + 1);
  let lo = 0;
  for (let i = 0; i < n; i++) {
    const d = (i / (n - 1)) * poly.length;
    while (lo < poly.cum.length - 2 && poly.cum[lo + 1]! < d) lo++;
    const hi = Math.min(lo + 1, poly.cum.length - 1);
    const t =
      (d - poly.cum[lo]!) / Math.max(1e-6, poly.cum[hi]! - poly.cum[lo]!);
    const x = poly.pts[2 * lo]! + (poly.pts[2 * hi]! - poly.pts[2 * lo]!) * t;
    const z =
      poly.pts[2 * lo + 1]! +
      (poly.pts[2 * hi + 1]! - poly.pts[2 * lo + 1]!) * t;
    let h = FLY.eyeM;
    if (meshes.length) {
      ray.set(new Vector3(x, 1500, z), down);
      const hit = ray.intersectObjects(meshes, false)[0];
      if (hit && hit.point.y > 1) h = hit.point.y + FLY.roofClearM;
    }
    raw.push({ x, z, h });
  }
  // dilate (so we rise BEFORE reaching a roof) then smooth
  const W = 4;
  const dil = raw.map((_, i) =>
    Math.max(...raw.slice(Math.max(0, i - W), i + W + 1).map((r) => r.h)),
  );
  const sm = dil.map((_, i) => {
    const s = dil.slice(Math.max(0, i - W), i + W + 1);
    return s.reduce((a, b) => a + b, 0) / s.length;
  });
  return raw.map((r, i) => [r.x, Math.max(FLY.eyeM, sm[i]!), r.z] as V3);
}

export function frameRouteView(r: Route) {
  let x0 = Infinity,
    x1 = -Infinity,
    z0 = Infinity,
    z1 = -Infinity;
  for (const s of r.segments)
    for (const [x, z] of s.geometry) {
      x0 = Math.min(x0, x);
      x1 = Math.max(x1, x);
      z0 = Math.min(z0, z);
      z1 = Math.max(z1, z);
    }
  // steep (~55 deg) three-quarter view so streets between towers stay visible
  const ext = Math.max(x1 - x0, z1 - z0, 250);
  const dist = ext * 1.15;
  return presetFrom(
    [(x0 + x1) / 2, 0, (z0 + z1) / 2 + ext * 0.05],
    200,
    dist,
    dist * 1.45,
    34,
  );
}

export function AppDrivers() {
  const scene = useThree((s) => s.scene);
  const flyRef = useRef<{
    route: Route;
    poly: RoutePolyline;
    durS: number;
    departMin: number;
  } | null>(null);
  const flyT = useRoute((s) => s.flyT);

  // start / stop the fly-through rig
  useEffect(() => {
    const st = useRoute.getState();
    if (flyT === null) {
      if (flyRef.current) {
        flyRef.current = null;
        useRig.getState().setRig(null);
        setIndoorAmount(0);
      }
      return;
    }
    if (flyRef.current) return;
    const route = st.result?.[st.selected];
    if (!route) return;
    const poly = routePolyline(route);
    const path = authorFlyPath(poly, useCity.getState().buildings);
    const durS = Math.min(
      FLY.maxS,
      Math.max(FLY.minS, poly.length / FLY.speedMps),
    );
    const dep = route.depart.match(/T(\d\d):(\d\d)/);
    const departMin = dep
      ? hhmmToMinutes(`${dep[1]}${dep[2]}`)
      : useSun.getState().minutes;
    flyRef.current = { route, poly, durS, departMin };
    const params = {
      points: path,
      lookahead: 34,
      fov: 40,
      floatAmp: 0.08,
      seed: 4,
      durationS: durS,
      accel: FLY_ACCEL,
    };
    useRig.getState().setRig({ id: "fly", evaluate: (t) => flyRig(t, params) });
  }, [flyT, scene]);

  useFrame((_, delta) => {
    const stage = useStage.getState();
    if (stage.mode !== "app") return;
    const dt = Math.min(delta, 0.1);
    stage.setFrameT(stage.frameT + dt);

    const sun = useSun.getState();
    if (sun.playing) {
      let m = sun.minutes + dt * FLY.timelapseMinPerS;
      const end = Math.ceil(sun.sunset + 20);
      if (m > end) m = Math.floor(sun.sunrise - 20);
      sun.setMinutes(m);
    }

    const f = flyRef.current;
    const rs = useRoute.getState();
    if (f && rs.flyT !== null) {
      const t = Math.min(1, rs.flyT + dt / f.durS);
      // the rig eases distance along the path; the traveller's clock follows the same eased
      // fraction (route speed is uniform per mode, so distance fraction ~= time fraction)
      useRig.getState().setT(t);
      const p = progressAt(f.route, easedDistance(t, FLY_ACCEL));
      // sun follows the traveller's clock
      sun.setMinutes(f.departMin + p.elapsedS / 60);
      setIndoorAmount(p.cls === "indoor" || p.cls === "ac_link" ? 0.4 : 0);
      if (t >= 1) {
        rs.setFlyT(null);
        useRig.getState().setView(frameRouteView(f.route));
      } else rs.setFlyT(t);
    }
  });

  return null;
}
