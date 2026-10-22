"use client";
// Post stack (PRD 12.5) by quality tier:
//   high:   N8AO (low) -> bloom (very subtle, high threshold: sun disc + dusk windows only)
//           -> AgX tone mapping -> grade/vignette/grain (MSAA 4)
//   medium: bloom -> tone mapping -> grade (MSAA 2)
//   low:    tone mapping -> grade
import {
  Bloom,
  EffectComposer,
  N8AO,
  ToneMapping,
} from "@react-three/postprocessing";
import { useFrame } from "@react-three/fiber";
import { ToneMappingMode } from "postprocessing";
import { useMemo } from "react";
import { Vector3 } from "three";
import { useStage } from "@/state/stage";
import { TIERS } from "../sceneConfig";
import { currentLighting, getIndoorAmount } from "../useLighting";
import { GradeEffect } from "./GradeEffect";

export function Post() {
  const quality = useStage((s) => s.quality);
  const tier = TIERS[quality];
  const grade = useMemo(() => new GradeEffect(), []);

  useFrame(() => {
    const L = currentLighting();
    (grade.uniforms.get("uTint")!.value as Vector3).set(...L.tint);
    grade.set("uSaturation", L.saturation);
    grade.set("uContrast", L.contrast);
    grade.set("uGain", Math.pow(2, L.exposure));
    grade.set("uIndoor", getIndoorAmount());
    // deterministic grain: seeded by the stage's frame-t (the Film sets it; the App advances it)
    grade.set("uSeed", Math.floor(useStage.getState().frameT * 24) % 997);
  });

  return (
    <EffectComposer key={quality} multisampling={tier.msaa}>
      <>
        {tier.ao ? (
          <N8AO
            aoRadius={6}
            distanceFalloff={1.5}
            intensity={1.6}
            quality="low"
            halfRes
          />
        ) : null}
        {tier.bloom ? (
          <Bloom
            mipmapBlur
            luminanceThreshold={1.6}
            luminanceSmoothing={0.3}
            intensity={0.32}
            radius={0.6}
          />
        ) : null}
        <ToneMapping mode={ToneMappingMode.AGX} />
        <primitive object={grade} />
      </>
    </EffectComposer>
  );
}
