"use client";
// Applies the active rig's state to the camera every frame (rig = pure function of `t` from the
// store; no internal timers). With no rig active, interactive MapControls own the camera.
import { MapControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { PerspectiveCamera, Vector3 } from "three";
import type { MapControls as MapControlsImpl } from "three-stdlib";
import { useRig } from "@/state/rig";
import { setCameraFocus } from "./focus";
import { CAMERA_PRESETS, SCENE } from "./sceneConfig";

const tmpTarget = new Vector3();
const tmpDir = new Vector3();

export function CameraDriver({
  interactive = true,
}: {
  interactive?: boolean;
}) {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const controls = useRef<MapControlsImpl>(null);
  const rig = useRig((s) => s.rig);
  const view = useRig((s) => s.view);

  // initial placement
  useEffect(() => {
    if (useRig.getState().view) return;
    const p = CAMERA_PRESETS.default!;
    useRig.getState().setView(p);
  }, []);

  // one-shot view placement (presets, QA, "reset")
  useEffect(() => {
    if (!view) return;
    camera.position.set(...view.position);
    camera.fov = view.fov;
    camera.up.set(0, 1, 0);
    camera.updateProjectionMatrix();
    camera.lookAt(...view.target);
    const c = controls.current;
    if (c) {
      c.target.set(...view.target);
      c.update();
    }
    setCameraFocus(view.target[0], view.target[1], view.target[2]);
  }, [view, camera]);

  useFrame(() => {
    // dynamic near plane: depth precision where it matters (street level vs. 2 km aerials)
    const near = Math.min(
      SCENE.nearMax,
      Math.max(SCENE.nearMin, camera.position.y * 0.25),
    );
    if (Math.abs(camera.near - near) / camera.near > 0.15) {
      camera.near = near;
      camera.updateProjectionMatrix();
    }
    const r = useRig.getState().rig;
    if (r) {
      const s = r.evaluate(useRig.getState().t);
      camera.position.set(...s.position);
      camera.up.set(0, 1, 0);
      camera.lookAt(...s.target);
      if (s.roll) camera.rotateZ(s.roll);
      if (Math.abs(camera.fov - s.fov) > 1e-4) {
        camera.fov = s.fov;
        camera.updateProjectionMatrix();
      }
      // shadow focus: a point ~120 m ahead of the camera on the ground plane
      tmpTarget.set(...s.target);
      tmpDir
        .copy(tmpTarget)
        .sub(camera.position)
        .setY(0)
        .normalize()
        .multiplyScalar(120);
      setCameraFocus(
        camera.position.x + tmpDir.x,
        0,
        camera.position.z + tmpDir.z,
      );
    } else if (controls.current) {
      const t = controls.current.target;
      setCameraFocus(t.x, 0, t.z);
    }
  });

  return interactive ? (
    <MapControls
      ref={controls}
      enabled={!rig}
      enableDamping
      dampingFactor={0.08}
      screenSpacePanning={false}
      minDistance={25}
      maxDistance={7000}
      maxPolarAngle={Math.PI * 0.495}
      zoomSpeed={0.8}
      makeDefault
    />
  ) : null;
}
