"use client";
// The authoritative visual of the product (PRD 13.1.3): the baked sun_fraction raster on the
// ground, blended between the two nearest 10-minute steps by time fraction. Same raster the
// router uses, so the picture and the numbers cannot disagree.
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import {
  ClampToEdgeWrapping,
  LinearFilter,
  LinearMipmapLinearFilter,
  NoColorSpace,
  ShaderMaterial,
  Texture,
  TextureLoader,
  UniformsLib,
  UniformsUtils,
} from "three";
import { shadeStepUrl } from "@/lib/assets";
import { hhmmToMinutes } from "@/lib/sun";
import { useCity } from "@/state/city";
import { useStage } from "@/state/stage";
import { useSun } from "@/state/sun";
import { SHADE_GLSL, shadeUniforms } from "./shadeUniforms";

// ---------------------------------------------------------------------------------------------
// texture cache (LRU)
type Entry = { tex: Texture; ready: boolean; failed: boolean; used: number };
const cache = new Map<string, Entry>();
const loader = new TextureLoader();
const MAX_TEX = 18;
let useClock = 0;

function request(url: string): Entry {
  const e = cache.get(url);
  if (e) {
    e.used = ++useClock;
    return e;
  }
  const entry: Entry = {
    tex: new Texture(),
    ready: false,
    failed: false,
    used: ++useClock,
  };
  cache.set(url, entry);
  loader.load(
    url,
    (tex) => {
      tex.flipY = false; // PNG row 0 = north = v 0 (CONTRACTS 2)
      tex.colorSpace = NoColorSpace; // data, not colour
      tex.wrapS = ClampToEdgeWrapping;
      tex.wrapT = ClampToEdgeWrapping;
      tex.magFilter = LinearFilter;
      tex.minFilter = LinearMipmapLinearFilter;
      tex.generateMipmaps = true;
      tex.anisotropy = 8;
      tex.needsUpdate = true;
      entry.tex = tex;
      entry.ready = true;
    },
    undefined,
    () => {
      entry.failed = true;
    },
  );
  if (cache.size > MAX_TEX) {
    const victims = [...cache.entries()]
      .filter(([, v]) => v.ready)
      .sort((a, b) => a[1].used - b[1].used);
    for (const [k, v] of victims.slice(0, cache.size - MAX_TEX)) {
      v.tex.dispose();
      cache.delete(k);
    }
  }
  return entry;
}

export function shadeTexturesReady(urls: string[]): boolean {
  return urls.every((u) => cache.get(u)?.ready);
}

// ---------------------------------------------------------------------------------------------
const vertex = /* glsl */ `
varying vec3 vWorld;
#include <fog_pars_vertex>
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vWorld = wp.xyz;
  vec4 mvPosition = viewMatrix * wp;
  gl_Position = projectionMatrix * mvPosition;
  #include <fog_vertex>
}
`;

const fragment = /* glsl */ `
varying vec3 vWorld;
${SHADE_GLSL}
#include <fog_pars_fragment>
void main() {
  vec3 c = zillGround(vWorld.xz);
  gl_FragColor = vec4(c, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <fog_fragment>
}
`;

export function makeGroundMaterial(extraFragment = ""): ShaderMaterial {
  const m = new ShaderMaterial({
    uniforms: UniformsUtils.merge([UniformsLib.fog]),
    vertexShader: vertex,
    fragmentShader: extraFragment || fragment,
    fog: true,
  });
  // share (not clone) the shade uniforms so one update drives every ground-layer material
  Object.assign(m.uniforms, shadeUniforms);
  return m;
}

/** Drives the shared shade uniforms from the sun clock. Mount once. */
export function ShadeDriver() {
  const meta = useCity((s) => s.meta);
  const cityId = useCity((s) => s.cityId);
  const ensure = useCity((s) => s.ensureShadeIndex);
  const dateKey = useSun((s) => s.dateKey);
  const index = useCity((s) => s.shadeIndex[dateKey]);

  useEffect(() => {
    if (!meta) return;
    const g = meta.core_grid;
    shadeUniforms.uGridOrigin.value.set(g.x0, g.z0);
    shadeUniforms.uGridSize.value.set(g.cols * g.res_m, g.rows * g.res_m);
    shadeUniforms.uTexel.value.set(1 / g.cols, 1 / g.rows);
  }, [meta]);

  useEffect(() => {
    if (meta) void ensure(dateKey);
  }, [meta, dateKey, ensure]);

  const steps = useMemo(
    () =>
      index
        ? index.steps.map((s) => ({
            ...s,
            m: hhmmToMinutes(s.hhmm),
            url: shadeStepUrl(cityId, dateKey, s.file),
          }))
        : [],
    [index, cityId, dateKey],
  );

  useFrame((_, delta) => {
    if (steps.length === 0) {
      shadeUniforms.uShadeOpacity.value = Math.max(
        0,
        shadeUniforms.uShadeOpacity.value - delta * 2,
      );
      return;
    }
    const m = useSun.getState().minutes;
    let i = 0;
    while (i < steps.length - 1 && steps[i + 1]!.m <= m) i++;
    const s0 = steps[i]!;
    const s1 = steps[Math.min(i + 1, steps.length - 1)]!;
    const frac =
      s1.m > s0.m ? Math.min(1, Math.max(0, (m - s0.m) / (s1.m - s0.m))) : 0;
    // prefetch +-3 steps around the current pair
    for (
      let k = Math.max(0, i - 3);
      k <= Math.min(steps.length - 1, i + 4);
      k++
    )
      request(steps[k]!.url);
    const a = request(s0.url);
    const b = request(s1.url);
    if (a.ready && b.ready) {
      shadeUniforms.uShadeA.value = a.tex;
      shadeUniforms.uShadeB.value = b.tex;
      shadeUniforms.uShadeMix.value = frac;
    } else if (a.ready) {
      shadeUniforms.uShadeA.value = a.tex;
      shadeUniforms.uShadeB.value = a.tex;
      shadeUniforms.uShadeMix.value = 0;
    } else if (b.ready) {
      shadeUniforms.uShadeA.value = b.tex;
      shadeUniforms.uShadeB.value = b.tex;
      shadeUniforms.uShadeMix.value = 0;
    }
    const anyShown =
      a.ready || b.ready || shadeUniforms.uShadeOpacity.value > 0;
    const target =
      a.ready || b.ready ? 1 : anyShown ? shadeUniforms.uShadeOpacity.value : 0;
    const op = shadeUniforms.uShadeOpacity.value;
    const qa = useStage.getState().qa;
    shadeUniforms.uShadeOpacity.value = qa
      ? target
      : op + (target - op) * Math.min(1, delta * 3);
    const ready = a.ready && b.ready;
    if (useStage.getState().shadeReady !== ready)
      useStage.getState().setShadeReady(ready);
  });

  return null;
}

/** Ground plane: core grid carries the raster; beyond it a quiet plinth fading into the haze. */
export function ShadeGround() {
  const material = useMemo(() => makeGroundMaterial(), []);
  return (
    <mesh
      rotation-x={-Math.PI / 2}
      position={[0, 0, 0]}
      material={material}
      renderOrder={-1}
      receiveShadow={false}
    >
      <planeGeometry args={[60000, 60000, 1, 1]} />
    </mesh>
  );
}
