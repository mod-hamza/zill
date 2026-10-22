"use client";
// Streets and paths from graph.json as faint, slightly lighter ribbons, merged into ONE geometry.
// They sample the same shade raster as the ground, so shade reads continuously across them.
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import { DoubleSide, ShaderMaterial, UniformsLib, UniformsUtils } from "three";
import { buildRibbons, type RibbonLine } from "@/lib/graph";
import { useCity } from "@/state/city";
import { RIBBON_VERTEX, ribbonGeometry } from "./ribbon";
import { SHADE_GLSL, shadeUniforms } from "./shadeUniforms";
import { SCENE } from "./sceneConfig";

const WIDTH: Record<string, number> = {
  footway: 2.2,
  path: 2.2,
  pedestrian: 5,
  steps: 2.2,
  corridor: 2.2,
  cycleway: 2.5,
  living_street: 6,
  residential: 7,
  service: 5,
  unclassified: 7,
  tertiary: 9,
  secondary: 11,
  primary: 13,
  trunk: 15,
};

const fragment = /* glsl */ `
varying float vSide;
varying float vDist;
varying float vValue;
varying vec3 vWorld;
uniform float uLift;
${SHADE_GLSL}
#include <fog_pars_fragment>
void main() {
  vec3 g = zillGround(vWorld.xz);
  // faint lighter ribbon with a soft edge (no hard outline)
  float edge = smoothstep(1.0, 0.55, abs(vSide));
  vec3 c = g * mix(1.0, uLift, edge) + vec3(0.004, 0.0035, 0.003) * edge;
  gl_FragColor = vec4(c, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <fog_fragment>
}
`;

export function Roads() {
  const graph = useCity((s) => s.graph);
  const size = useThree((s) => s.size);
  const material = useMemo(() => {
    const m = new ShaderMaterial({
      uniforms: UniformsUtils.merge([
        UniformsLib.fog,
        {
          uLiftPerM: { value: 0.00012 },
          uWidthScale: { value: 1 },
          uMinPx: { value: 0.0 },
          uViewportH: { value: 1080 },
          uLift: { value: SCENE.roadLift },
        },
      ]),
      vertexShader: RIBBON_VERTEX,
      fragmentShader: fragment,
      fog: true,
      side: DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -2,
    });
    Object.assign(m.uniforms, shadeUniforms);
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
      const geom = e.geom[i];
      if (!geom || geom.length < 4) continue;
      lines.push({ pts: geom, width: WIDTH[e.highway[i] ?? ""] ?? 3 });
    }
    return ribbonGeometry(buildRibbons(lines, SCENE.roadY));
  }, [graph]);

  if (!geometry) return null;
  return (
    <mesh
      geometry={geometry}
      material={material}
      frustumCulled={false}
      renderOrder={0}
    />
  );
}
