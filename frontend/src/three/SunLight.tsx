"use client";
// One DirectionalLight from lib/sun.ts with a shadow camera fitted to a ~600 m box around the
// camera focus (texel-snapped against shimmer), plus a hemisphere sky light. Also pushes the
// time-of-day ground colours into the shared shade uniforms.
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { DirectionalLight, HemisphereLight, Object3D, Vector3 } from "three";
import { useStage } from "@/state/stage";
import { useSun } from "@/state/sun";
import { SCENE, TIERS } from "./sceneConfig";
import { shadeUniforms } from "./shadeUniforms";
import { currentLighting } from "./useLighting";
import { cameraFocus } from "./focus";

export function SunLight() {
  const quality = useStage((s) => s.quality);
  const tier = TIERS[quality];
  const light = useRef<DirectionalLight>(null);
  const hemi = useRef<HemisphereLight>(null);
  const target = useMemo(() => new Object3D(), []);
  const tmp = useMemo(() => new Vector3(), []);

  useEffect(() => {
    const l = light.current;
    if (!l) return;
    l.target = target;
    const half = SCENE.shadowBoxM / 2;
    const cam = l.shadow.camera;
    cam.left = -half;
    cam.right = half;
    cam.top = half;
    cam.bottom = -half;
    cam.near = 10;
    cam.far = SCENE.shadowDistM * 2;
    cam.updateProjectionMatrix();
    l.shadow.mapSize.set(tier.shadowMap, tier.shadowMap);
    l.shadow.bias = -0.0004;
    l.shadow.normalBias = 0.6;
    l.shadow.radius = 3;
    if (l.shadow.map) {
      l.shadow.map.dispose();
      l.shadow.map = null;
    }
  }, [tier.shadowMap, target]);

  useFrame(() => {
    const L = currentLighting();
    const v = useSun.getState().sun.vector;
    const l = light.current;
    if (l) {
      // focus snapped to shadow texels so the map does not shimmer while the camera moves
      const f = cameraFocus();
      const texel = SCENE.shadowBoxM / tier.shadowMap;
      tmp.set(
        Math.round(f.x / texel) * texel,
        0,
        Math.round(f.z / texel) * texel,
      );
      target.position.copy(tmp);
      target.updateMatrixWorld();
      l.position.set(
        tmp.x + v[0] * SCENE.shadowDistM,
        v[1] * SCENE.shadowDistM,
        tmp.z + v[2] * SCENE.shadowDistM,
      );
      l.color.setRGB(...L.sunColor);
      const up = v[1] > 0.02;
      l.intensity = up ? L.sunIntensity : 0;
      l.castShadow = tier.shadows && up;
    }
    const h = hemi.current;
    if (h) {
      h.color.setRGB(...L.hemiSky);
      h.groundColor.setRGB(...L.hemiGround);
      h.intensity = L.hemiIntensity;
    }
    shadeUniforms.uGroundSun.value.setRGB(...L.groundSun);
    shadeUniforms.uGroundShade.value.setRGB(...L.groundShade);
    shadeUniforms.uSunDir.value.set(v[0], v[1], v[2]);
    // the plinth beyond the modelled area: dark warm stone, quieter than any modelled ground
    // (a muted mid tone so it melts into the horizon haze instead of reading as a dark band)
    shadeUniforms.uOutside.value.setRGB(
      (L.groundSun[0] * 0.35 + L.groundShade[0] * 0.65) * 0.7,
      (L.groundSun[1] * 0.35 + L.groundShade[1] * 0.65) * 0.7,
      (L.groundSun[2] * 0.35 + L.groundShade[2] * 0.65) * 0.7,
    );
  });

  return (
    <>
      <directionalLight ref={light} castShadow={tier.shadows} />
      <primitive object={target} />
      <hemisphereLight ref={hemi} />
    </>
  );
}
