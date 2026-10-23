"use client";
// Covered / indoor / air-conditioned links: thin oasis ribbons with a faint inner warm glow.
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import {
  Color,
  DoubleSide,
  ShaderMaterial,
  UniformsLib,
  UniformsUtils,
} from "three";
import { colors } from "@/design/tokens";
import { buildRibbons, type RibbonLine } from "@/lib/graph";
import { useCity } from "@/state/city";
import { RIBBON_VERTEX, ribbonGeometry } from "./ribbon";
import { SCENE } from "./sceneConfig";
import { currentLighting } from "./useLighting";

const fragment = /* glsl */ `
varying float vSide;
varying float vDist;
varying float vValue;
varying vec3 vWorld;
uniform vec3 uOasis;
uniform vec3 uWarm;
uniform float uLevel;
uniform float uHighlight;
uniform float uVis;
#include <fog_pars_fragment>
void main() {
  float s = abs(vSide);
  float body = 1.0 - smoothstep(0.82, 1.0, s);
  float core = exp(-s * s * 18.0);
  vec3 c = uOasis * uLevel * (0.85 + 0.35 * uHighlight) + uWarm * core * (0.16 + 0.5 * uHighlight);
  gl_FragColor = vec4(c, body * 0.92 * uVis);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <fog_fragment>
}
`;

/** uHighlight: Film emphasis; uVis: Film reveal (1 = visible, the /app default) */
export const linkUniforms = {
  uHighlight: { value: 0 },
  uVis: { value: 1 },
  uMinPx: { value: 1.1 },
};

export function Links() {
  const graph = useCity((s) => s.graph);
  const size = useThree((s) => s.size);
  const material = useMemo(() => {
    const m = new ShaderMaterial({
      uniforms: UniformsUtils.merge([
        UniformsLib.fog,
        {
          uLiftPerM: { value: 0.00022 },
          uWidthScale: { value: 1 },
          uMinPx: { value: 1.1 },
          uViewportH: { value: 1080 },
          uOasis: { value: new Color(colors.oasis) },
          uWarm: { value: new Color(colors.champagne) },
          uLevel: { value: 1 },
        },
      ]),
      vertexShader: RIBBON_VERTEX,
      fragmentShader: fragment,
      fog: true,
      transparent: true,
      depthWrite: false,
      side: DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -4,
    });
    Object.assign(m.uniforms, linkUniforms);
    return m;
  }, []);
  useEffect(() => {
    material.uniforms.uViewportH!.value = size.height;
  }, [size.height, material]);

  const geometry = useMemo(() => {
    if (!graph) return null;
    const e = graph.raw.edges;
    const lines: RibbonLine[] = [];
    for (let i = 0; i < e.u.length; i++) {
      const cls = e.cls[i];
      if (cls === "open" || !cls) continue;
      const geom = e.geom[i];
      if (!geom || geom.length < 4) continue;
      lines.push({ pts: geom, width: cls === "covered" ? 3.5 : 4.5 });
    }
    if (lines.length === 0) return null;
    return ribbonGeometry(buildRibbons(lines, SCENE.linkY));
  }, [graph]);

  useFrame(() => {
    const L = currentLighting();
    material.uniforms.uLevel!.value =
      0.55 + 0.45 * Math.min(1, L.hemiIntensity / 0.7);
  });

  if (!geometry) return null;
  return (
    <mesh
      geometry={geometry}
      material={material}
      frustumCulled={false}
      renderOrder={2}
    />
  );
}
