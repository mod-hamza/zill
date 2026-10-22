"use client";
// Buildings from buildings.glb (one mesh per 250 m tile, frustum-culled per tile).
// ONE material: matte warm stone with a small shader layer (PRD 13.1.1):
//   per-building +-4% lightness from _BUILDING_ID hash (warm hues only), lighter roofs,
//   very-low-contrast vertical window lines, ground-contact darkening in the first ~6 m,
//   tungsten windows on ~35% of floors at dusk (driven by the `uDusk` uniform).
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import {
  BufferGeometry,
  Color,
  Mesh,
  MeshStandardMaterial,
  type Object3D,
} from "three";
import { useCity } from "@/state/city";
import { SCENE } from "./sceneConfig";
import { currentLighting } from "./useLighting";

export const buildingUniforms = {
  uDusk: { value: 0 },
  uTungsten: { value: new Color(SCENE.tungsten) },
  uWindowPitch: { value: SCENE.windowPitchM },
  uFloorH: { value: SCENE.floorM },
  uLitFrac: { value: SCENE.windowLitFraction },
  uAoH: { value: SCENE.aoHeightM },
};

const HASH = /* glsl */ `
float zh11(float p) { p = fract(p * 0.1031); p *= p + 33.33; p *= p + p; return fract(p); }
float zh12(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
`;

export function makeBuildingMaterial(): MeshStandardMaterial {
  const m = new MeshStandardMaterial({
    color: new Color(SCENE.stone),
    roughness: SCENE.roughness,
    metalness: 0,
  });
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, buildingUniforms);
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
attribute float aBid;
attribute float aTop;
varying vec3 vZW;
varying vec3 vZN;
varying float vBid;
varying float vTop;`,
      )
      .replace(
        "#include <fog_vertex>",
        `#include <fog_vertex>
vZW = (modelMatrix * vec4(transformed, 1.0)).xyz;
vZN = normalize(mat3(modelMatrix) * objectNormal);
vBid = aBid;
vTop = aTop;`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
uniform float uDusk;
uniform vec3 uTungsten;
uniform float uWindowPitch;
uniform float uFloorH;
uniform float uLitFrac;
uniform float uAoH;
varying vec3 vZW;
varying vec3 vZN;
varying float vBid;
varying float vTop;
${HASH}`,
      )
      .replace(
        "#include <color_fragment>",
        `#include <color_fragment>
float zRoof = smoothstep(0.55, 0.9, vZN.y);
float zWall = 1.0 - zRoof;
float zh = zh11(vBid * 1.618 + 0.37);
float zh2 = zh11(vBid * 7.31 + 2.1);
// +-4% lightness, warm-only hue drift (towards honey, never towards blue)
diffuseColor.rgb *= (0.96 + 0.08 * zh) * mix(vec3(1.0), vec3(1.035, 1.0, 0.94), zh2);
diffuseColor.rgb *= mix(1.0, 1.1, zRoof);
vec2 zT = normalize(vec2(-vZN.z, vZN.x) + vec2(1e-5));
float zU = dot(vZW.xz, zT);
float zCol = fract(zU / uWindowPitch);
float zLine = smoothstep(0.0, 0.03, zCol) * (1.0 - smoothstep(0.06, 0.1, zCol));
float zFy = fract(vZW.y / uFloorH);
float zFloorLine = smoothstep(0.0, 0.04, zFy) * (1.0 - smoothstep(0.06, 0.1, zFy));
diffuseColor.rgb *= 1.0 - zWall * (0.075 * zLine + 0.035 * zFloorLine) * step(4.0, vZW.y);
// ground-contact darkening (cheap AO) on walls
float zAo = mix(0.58, 1.0, smoothstep(0.0, uAoH, vZW.y));
diffuseColor.rgb *= mix(1.0, zAo, zWall);`,
      )
      .replace(
        "#include <emissivemap_fragment>",
        `#include <emissivemap_fragment>
if (uDusk > 0.001) {
  float fl = floor(vZW.y / uFloorH);
  float cu = floor(zU / uWindowPitch);
  float litFloor = step(zh12(vec2(vBid * 0.731 + 3.0, fl)), uLitFrac);
  float litWin = step(zh12(vec2(vBid * 1.37 + fl * 0.17, cu)), 0.55);
  float win = smoothstep(0.2, 0.26, zFy) * (1.0 - smoothstep(0.8, 0.86, zFy))
            * smoothstep(0.12, 0.18, zCol) * (1.0 - smoothstep(0.86, 0.92, zCol));
  float band = step(4.0, vZW.y) * step(vZW.y, vTop - 2.5);
  float var = 0.55 + 0.9 * zh12(vec2(cu, fl + vBid));
  totalEmissiveRadiance += uTungsten * (uDusk * litFloor * litWin * win * band * zWall * var * 0.85);
}`,
      );
  };
  m.customProgramCacheKey = () => "zill-building-v1";
  return m;
}

export function CityBuildings() {
  const scene = useCity((s) => s.buildings);
  const material = useMemo(() => makeBuildingMaterial(), []);

  const meshes = useMemo(() => {
    if (!scene) return [];
    const out: Mesh[] = [];
    scene.traverse((o: Object3D) => {
      const mesh = o as Mesh;
      if (!mesh.isMesh) return;
      const g = mesh.geometry as BufferGeometry;
      // GLTFLoader lower-cases custom attribute names: _BUILDING_ID -> _building_id
      const bid =
        g.getAttribute("_building_id") ?? g.getAttribute("_BUILDING_ID");
      const top = g.getAttribute("_height") ?? g.getAttribute("_HEIGHT");
      if (bid) g.setAttribute("aBid", bid);
      if (top) g.setAttribute("aTop", top);
      if (!g.getAttribute("normal")) g.computeVertexNormals();
      g.computeBoundingSphere();
      mesh.material = material;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.frustumCulled = true;
      mesh.matrixAutoUpdate = false;
      mesh.updateMatrix();
      out.push(mesh);
    });
    return out;
  }, [scene, material]);

  useEffect(() => () => material.dispose(), [material]);

  useFrame(() => {
    buildingUniforms.uDusk.value = currentLighting().dusk;
  });

  if (!scene) return null;
  return (
    <primitive
      object={scene}
      dispose={null}
      userData={{ meshes: meshes.length }}
    />
  );
}
