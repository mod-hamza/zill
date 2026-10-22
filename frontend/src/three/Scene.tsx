"use client";
// The ONE persistent <Canvas> shared by /film and /app (PRD 13). Tone mapping happens in the post
// stack (ACES), output is sRGB, shadows on, DPR by quality tier.
import { Canvas } from "@react-three/fiber";
import { PCFShadowMap, SRGBColorSpace } from "three";
import { useStage } from "@/state/stage";
import { SCENE, TIERS, CAMERA_PRESETS } from "./sceneConfig";
import { World } from "./World";

export function Scene() {
  const quality = useStage((s) => s.quality);
  const tier = TIERS[quality];
  const p = CAMERA_PRESETS.default!;
  return (
    <Canvas
      dpr={[1, tier.dpr]}
      shadows={{ type: PCFShadowMap, enabled: true }}
      gl={{
        antialias: false,
        powerPreference: "high-performance",
        alpha: false,
        stencil: false,
        preserveDrawingBuffer: false,
      }}
      camera={{
        fov: p.fov,
        near: SCENE.near,
        far: SCENE.far,
        position: p.position,
      }}
      onCreated={({ gl }) => {
        gl.outputColorSpace = SRGBColorSpace;
      }}
      style={{ position: "absolute", inset: 0 }}
    >
      <World />
    </Canvas>
  );
}
