"use client";
// The city world: every layer of PRD 13.1, composed once inside the persistent canvas.
import { useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect } from "react";
import { useCity } from "@/state/city";
import { useRig } from "@/state/rig";
import { useRoute } from "@/state/route";
import { useStage } from "@/state/stage";
import { AppDrivers } from "./AppDrivers";
import { CameraDriver } from "./CameraDriver";
import { CityBuildings } from "./CityBuildings";
import { Links } from "./Links";
import { Markers } from "./Markers";
import { Perf } from "./Perf";
import { Post } from "./post/Post";
import { Roads } from "./Roads";
import { Routes } from "./Routes";
import { ShadeDriver, ShadeGround } from "./ShadeGround";
import { Sky } from "./Sky";
import { SunLight } from "./SunLight";
import { Trees } from "./Trees";

function GroundPicker() {
  // invisible pick plane over the core grid (clicks set A then B, snapped to the graph)
  const meta = useCity((s) => s.meta);
  const mode = useStage((s) => s.mode);
  if (!meta || mode !== "app") return null;
  const g = meta.core_grid;
  const w = g.cols * g.res_m;
  const h = g.rows * g.res_m;
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    if (e.delta > 5 || useRig.getState().rig) return;
    const graph = useCity.getState().graph;
    if (!graph) return;
    const { mode: travel } = useRoute.getState();
    const i = graph.nearest(e.point.x, e.point.z, travel, 250);
    if (i < 0) return;
    e.stopPropagation();
    useRoute
      .getState()
      .clickPoint({
        node: i,
        x: graph.x[i]!,
        z: graph.z[i]!,
        lat: graph.lat[i]!,
        lon: graph.lon[i]!,
      });
  };
  return (
    <mesh
      rotation-x={-Math.PI / 2}
      position={[g.x0 + w / 2, 0.02, g.z0 + h / 2]}
      onClick={onClick}
      visible={false}
    >
      <planeGeometry args={[w, h]} />
      <meshBasicMaterial />
    </mesh>
  );
}

function RouteLayer() {
  const result = useRoute((s) => s.result);
  const view = useRoute((s) => s.view);
  const selected = useRoute((s) => s.selected);
  const flyT = useRoute((s) => s.flyT);
  const frameT = useStage((s) => s.frameT);
  const a = useRoute((s) => s.a);
  const b = useRoute((s) => s.b);
  return (
    <>
      <Routes
        result={result}
        view={view}
        selected={selected}
        t={frameT}
        travellerAt={flyT}
      />
      <Markers a={a} b={b} />
    </>
  );
}

function QaHandle() {
  // expose the scene to QA/debug tooling only (?qa or ?debug)
  const scene = useThree((s) => s.scene);
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    if (window.__zill) Object.assign(window.__zill, { scene, gl });
  }, [scene, gl]);
  return null;
}

export function World() {
  const load = useCity((s) => s.load);
  const mode = useStage((s) => s.mode);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <>
      <Sky />
      <SunLight />
      <ShadeDriver />
      <ShadeGround />
      <Roads />
      <Links />
      <CityBuildings />
      <Trees />
      <RouteLayer />
      <GroundPicker />
      <CameraDriver interactive={mode === "app"} />
      {mode === "app" ? <AppDrivers /> : null}
      <Post />
      <Perf />
      <QaHandle />
    </>
  );
}
