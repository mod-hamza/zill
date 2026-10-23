"use client";
// Physically-inspired sky (PRD 12.5): altitude-driven Rayleigh-ish gradient, soft sun disc at the
// TRUE azimuth/altitude (so shadows visibly point away from it), horizon haze. Also owns the fog.
import { useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { BackSide, Color, FogExp2, Mesh, ShaderMaterial, Vector3 } from "three";
import { useSun } from "@/state/sun";
import { currentLighting } from "./useLighting";
import { sceneOverrides } from "./sceneOverrides";

const vertex = /* glsl */ `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  gl_Position = p.xyww; // pin to the far plane
}
`;

const fragment = /* glsl */ `
varying vec3 vDir;
uniform vec3 uZenith;
uniform vec3 uHorizon;
uniform vec3 uFog;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform float uDisc;
uniform float uGlow;
uniform float uDim;
float zhash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
  vec3 d = normalize(vDir);
  float h = d.y;
  float up = clamp(h, 0.0, 1.0);
  vec3 col = mix(uHorizon, uZenith, pow(up, 0.5));
  // horizon haze band
  // (reaches the full fog colour AT the horizon so the fogged ground meets the sky without a seam)
  float hz = max(h, 0.0);
  col = mix(col, uFog, clamp(exp(-hz * 14.0) * 0.55 + exp(-hz * 70.0) * 0.45, 0.0, 1.0));
  // below the horizon: the haze the city sits in
  col = h < 0.0 ? mix(uFog, uFog * 0.7, clamp(-h * 6.0, 0.0, 1.0)) : col;
  float c = dot(d, normalize(uSunDir));
  // forward-scattering glow (Mie-ish), stronger near the horizon
  float glow = pow(max(c, 0.0), 10.0) * 0.22 + pow(max(c, 0.0), 120.0) * 0.5;
  col += uSunColor * glow * uGlow * (0.6 + 0.4 * exp(-up * 3.0));
  // soft sun disc (~0.6 deg radius core, soft rim)
  float ang = acos(clamp(c, -1.0, 1.0));
  float disc = 1.0 - smoothstep(0.0085, 0.0125, ang);
  float horizonCut = smoothstep(-0.01, 0.006, h);
  col += uSunColor * disc * uDisc * horizonCut;
  // Film: dim towards ink (Ch.4 build, Ch.11 globe); identity at 0
  col = mix(col, vec3(0.0046, 0.0039, 0.0032), uDim);
  // tiny dither against banding in the gradient
  col += (zhash(gl_FragCoord.xy) - 0.5) / 255.0;
  gl_FragColor = vec4(col, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

export function Sky() {
  const ref = useRef<Mesh>(null);
  const scene = useThree((s) => s.scene);
  const material = useMemo(
    () =>
      new ShaderMaterial({
        uniforms: {
          uZenith: { value: new Color() },
          uHorizon: { value: new Color() },
          uFog: { value: new Color() },
          uSunDir: { value: new Vector3(0, 1, 0) },
          uSunColor: { value: new Color() },
          uDisc: { value: 20 },
          uGlow: { value: 1 },
          uDim: { value: 0 },
        },
        vertexShader: vertex,
        fragmentShader: fragment,
        side: BackSide,
        depthWrite: false,
        depthTest: true,
        fog: false,
      }),
    [],
  );
  const fog = useMemo(() => new FogExp2(0xd6ccb8, 0.00017), []);

  useFrame(({ camera }) => {
    const L = currentLighting();
    const v = useSun.getState().sun.vector;
    const u = material.uniforms;
    (u.uZenith!.value as Color).setRGB(...L.zenith);
    (u.uHorizon!.value as Color).setRGB(...L.horizon);
    (u.uFog!.value as Color).setRGB(...L.fog);
    (u.uSunDir!.value as Vector3).set(v[0], v[1], v[2]);
    // the disc is drawn with the sun's colour but never dimmer than a warm white core
    const sc = u.uSunColor!.value as Color;
    sc.setRGB(...L.sunColor);
    if (L.sunIntensity <= 0) sc.setRGB(0, 0, 0);
    u.uDisc!.value = L.sunDisc;
    u.uGlow!.value = Math.min(1.4, 0.4 + L.sunIntensity * 0.3);
    const dim = sceneOverrides.skyDim;
    u.uDim!.value = dim;
    fog.color.setRGB(
      L.fog[0] * (1 - dim) + 0.0046 * dim,
      L.fog[1] * (1 - dim) + 0.0039 * dim,
      L.fog[2] * (1 - dim) + 0.0032 * dim,
    );
    fog.density = L.fogDensity * sceneOverrides.fogScale;
    if (scene.fog !== fog) scene.fog = fog;
    if (ref.current) ref.current.position.copy(camera.position);
  });

  return (
    <mesh ref={ref} material={material} frustumCulled={false} renderOrder={-10}>
      <sphereGeometry args={[30000, 48, 24]} />
    </mesh>
  );
}
