"use client";
// Buildings from buildings.glb (one mesh per 250 m tile, frustum-culled per tile).
// ONE material: matte warm stone with a small shader layer (PRD 13.1.1):
//   per-building +-4% lightness from _BUILDING_ID hash (warm hues only), lighter roofs,
//   very-low-contrast vertical window lines, ground-contact darkening in the first ~6 m,
//   tungsten windows on ~35% of floors at dusk (driven by the `uDusk` uniform).
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import {
  BufferAttribute,
  BufferGeometry,
  Color,
  Mesh,
  MeshStandardMaterial,
  type Object3D,
} from "three";
import { useCity } from "@/state/city";
import { SCENE } from "./sceneConfig";
import { currentLighting } from "./useLighting";
import { sceneOverrides } from "./sceneOverrides";

export const buildingUniforms = {
  uDusk: { value: 0 },
  uTungsten: { value: new Color(SCENE.tungsten) },
  uWindowPitch: { value: SCENE.windowPitchM },
  uFloorH: { value: SCENE.floorM },
  uLitFrac: { value: SCENE.windowLitFraction as number },
  uAoH: { value: SCENE.aoHeightM },
  /** Film Ch.4 radial rise (identity by default: everything risen) */
  uRevealR: { value: 1e9 },
  uRevealBand: { value: 260 },
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
attribute float aCDist;
uniform float uRevealR;
uniform float uRevealBand;
varying float vRise;
varying vec3 vZW;
varying vec3 vZN;
varying float vBid;
varying float vTop;`,
      )
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
float zRise = clamp((uRevealR - aCDist) / uRevealBand, 0.0, 1.0);
zRise = 1.0 - pow(1.0 - zRise, 3.0);
transformed.y *= max(zRise, 0.002);
vRise = zRise;`,
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
varying float vRise;
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
diffuseColor.rgb *= mix(1.0, zAo, zWall);
// Film Ch.4: footprints waiting to rise read as dim stone, brightening as they rise
diffuseColor.rgb *= mix(0.1, 1.0, smoothstep(0.0, 0.35, vRise));`,
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
  m.customProgramCacheKey = () => "zill-building-v3";
  return m;
}

export function CityBuildings() {
  const scene = useCity((s) => s.buildings);
  const material = useMemo(() => makeBuildingMaterial(), []);

  const meshes = useMemo(() => {
    if (!scene) return [];
    const out: Mesh[] = [];
    // per-building centroid distance from the origin (Film Ch.4 radial rise; harmless otherwise)
    const acc = new Map<number, [number, number, number]>();
    scene.traverse((o: Object3D) => {
      const mesh = o as Mesh;
      if (!mesh.isMesh) return;
      const g = mesh.geometry as BufferGeometry;
      const bid = g.getAttribute("_building_id") ?? g.getAttribute("_BUILDING_ID");
      const pos = g.getAttribute("position");
      if (!bid || !pos) return;
      mesh.updateWorldMatrix(true, false);
      const e = mesh.matrixWorld.elements;
      for (let i = 0; i < pos.count; i++) {
        const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
        const wx = e[0]! * x + e[4]! * y + e[8]! * z + e[12]!;
        const wz = e[2]! * x + e[6]! * y + e[10]! * z + e[14]!;
        const k = bid.getX(i);
        const a = acc.get(k);
        if (a) { a[0] += wx; a[1] += wz; a[2] += 1; } else acc.set(k, [wx, wz, 1]);
      }
    });
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
      if (bid && !g.getAttribute("aCDist")) {
        const d = new Float32Array(bid.count);
        for (let i = 0; i < bid.count; i++) {
          const a = acc.get(bid.getX(i));
          d[i] = a ? Math.hypot(a[0] / a[2], a[1] / a[2]) : 0;
        }
        g.setAttribute("aCDist", new BufferAttribute(d, 1));
      }
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
    buildingUniforms.uRevealR.value = sceneOverrides.revealRadius;
    buildingUniforms.uLitFrac.value = sceneOverrides.litFrac ?? SCENE.windowLitFraction;
    buildingUniforms.uRevealBand.value = sceneOverrides.revealBand;
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
