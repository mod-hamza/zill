"use client";
// Routes (PRD 13.1.7): ribbons hugging the ground (+0.15 m), ~1 m wide with a screen-space floor
// so they read from altitude.
//   analysis view     -> per-vertex exposure ramp shade -> #6F6A55 -> ember (OKLab, via ramp texture)
//   presentation view -> fastest = slate, coolest = brass with a slow travelling soft pulse
// The pulse and the traveller are driven by the `t` prop (seconds) — deterministic for the Film.
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  Color,
  DataTexture,
  DoubleSide,
  LinearFilter,
  Mesh,
  RGBAFormat,
  ShaderMaterial,
  UniformsLib,
  UniformsUtils,
  FloatType,
  ClampToEdgeWrapping,
  GreaterDepth,
} from "three";
import { colors } from "@/design/tokens";
import type { Route, RouteResponse } from "@/lib/api";
import { exposureColor } from "@/lib/color";
import { buildRibbons } from "@/lib/graph";
import { pointAt, routePolyline, type RoutePolyline } from "@/lib/routeGeom";
import type { RouteKey, RouteView } from "@/state/route";
import { RIBBON_VERTEX, ribbonGeometry } from "./ribbon";
import { SCENE } from "./sceneConfig";

function rampTexture(): DataTexture {
  const N = 64;
  const d = new Float32Array(N * 4);
  for (let i = 0; i < N; i++) {
    const c = exposureColor(i / (N - 1));
    d.set([c[0], c[1], c[2], 1], i * 4);
  }
  const t = new DataTexture(d, N, 1, RGBAFormat, FloatType);
  t.magFilter = LinearFilter;
  t.minFilter = LinearFilter;
  t.wrapS = ClampToEdgeWrapping;
  t.needsUpdate = true;
  return t;
}
const GHOST_OPACITY = 0.3;
const RAMP = typeof window !== "undefined" ? rampTexture() : null;

const fragment = /* glsl */ `
varying float vSide;
varying float vDist;
varying float vValue;
varying vec3 vWorld;
uniform vec3 uColor;
uniform float uUseRamp;
uniform sampler2D uRamp;
uniform float uOpacity;
uniform float uPulseOn;
uniform float uPulseAt;
uniform float uPulseW;
uniform vec3 uPulseColor;
uniform vec3 uBorder;
uniform float uGain;
#include <fog_pars_fragment>
void main() {
  float s = abs(vSide);
  vec3 base = uUseRamp > 0.5 ? texture2D(uRamp, vec2(clamp(vValue, 0.0, 1.0), 0.5)).rgb : uColor;
  // lift the ramp a touch so the shaded end still separates from shaded ground; a dark rim
  // gives the line an edge against bright sunlit paving
  vec3 c = base * uGain;
  float rim = smoothstep(0.6, 0.72, s);
  c = mix(c, uBorder, rim * 0.85);
  float p = uPulseOn * exp(-pow((vDist - uPulseAt) / uPulseW, 2.0));
  c = mix(c, uPulseColor, p * 0.55 * (1.0 - rim));
  float alpha = (1.0 - smoothstep(0.9, 1.0, s)) * uOpacity;
  gl_FragColor = vec4(c, alpha);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <fog_fragment>
}
`;

function makeMaterial(): ShaderMaterial {
  return new ShaderMaterial({
    uniforms: UniformsUtils.merge([
      UniformsLib.fog,
      {
        uLiftPerM: { value: 0.00035 },
        uWidthScale: { value: 1 },
        uMinPx: { value: 2.2 },
        uViewportH: { value: 1080 },
        uColor: { value: new Color(colors.brass) },
        uUseRamp: { value: 0 },
        uRamp: { value: null },
        uOpacity: { value: 1 },
        uPulseOn: { value: 0 },
        uPulseAt: { value: 0 },
        uPulseW: { value: 45 },
        uPulseColor: { value: new Color(colors.champagne) },
        uBorder: { value: new Color(colors.ink) },
        uGain: { value: 1.25 },
      },
    ]),
    vertexShader: RIBBON_VERTEX,
    fragmentShader: fragment,
    fog: true,
    transparent: true,
    depthWrite: false,
    side: DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -4,
    polygonOffsetUnits: -8,
  });
}

type Props = {
  result: RouteResponse | null;
  view: RouteView;
  selected: RouteKey;
  /** seconds; drives the travelling pulse deterministically */
  t: number;
  /** 0..1 along the selected route for the traveller marker, or null to hide */
  travellerAt?: number | null;
  /** which routes to draw in presentation view */
  presentationKeys?: RouteKey[];
};

const ORDER: RouteKey[] = ["fastest", "balanced", "coolest"];

function RouteRibbon({
  route,
  poly,
  style,
  t,
}: {
  route: Route;
  poly: RoutePolyline;
  style: Style;
  t: number;
}) {
  const size = useThree((s) => s.size);
  const material = useMemo(() => makeMaterial(), []);
  // "x-ray" ghost: the parts hidden behind buildings stay faintly readable (depth test inverted)
  const ghost = useMemo(() => {
    const m = makeMaterial();
    m.depthFunc = GreaterDepth;
    m.polygonOffset = false;
    return m;
  }, []);
  const geometry = useMemo(
    () =>
      ribbonGeometry(
        buildRibbons(
          [{ pts: poly.pts, width: style.width, values: poly.values }],
          SCENE.routeY + style.lift,
          true,
        ),
      ),
    [poly, style.width, style.lift],
  );
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);
  useEffect(() => () => ghost.dispose(), [ghost]);
  useEffect(() => {
    for (const m of [material, ghost]) {
      const u = m.uniforms;
      const isGhost = m === ghost;
      u.uViewportH!.value = size.height;
      (u.uColor!.value as Color).set(style.color);
      u.uUseRamp!.value = style.ramp ? 1 : 0;
      u.uRamp!.value = RAMP;
      u.uOpacity!.value = isGhost
        ? style.opacity * GHOST_OPACITY
        : style.opacity;
      u.uMinPx!.value = isGhost ? style.minPx * 0.8 : style.minPx;
      u.uPulseOn!.value = style.pulse && !isGhost ? 1 : 0;
      u.uGain!.value = style.ramp ? 1.35 : 1.15;
    }
  }, [material, ghost, style, size.height]);
  useFrame(() => {
    if (!style.pulse) return;
    // slow travelling highlight: ~70 m/s apparent, with a pause between passes
    const span = poly.length + 400;
    material.uniforms.uPulseAt!.value = ((t * 70) % span) - 200;
  });
  void route;
  return (
    <>
      <mesh
        geometry={geometry}
        material={ghost}
        frustumCulled={false}
        renderOrder={style.order - 5}
      />
      <mesh
        geometry={geometry}
        material={material}
        frustumCulled={false}
        renderOrder={style.order}
      />
    </>
  );
}

type Style = {
  color: string;
  ramp: boolean;
  opacity: number;
  width: number;
  minPx: number;
  pulse: boolean;
  order: number;
  lift: number;
};

function styleFor(
  k: RouteKey,
  view: RouteView,
  selected: RouteKey,
): Style | null {
  const isSel = k === selected;
  if (view === "analysis") {
    if (isSel)
      return {
        color: colors.ember,
        ramp: true,
        opacity: 1,
        width: 1.2,
        minPx: 2.6,
        pulse: false,
        order: 12,
        lift: 0.02,
      };
    return {
      color: colors.slate,
      ramp: false,
      opacity: 0.45,
      width: 0.9,
      minPx: 1.3,
      pulse: false,
      order: 10,
      lift: 0,
    };
  }
  if (k === "balanced" && !isSel) return null;
  const color =
    k === "fastest"
      ? colors.slate
      : k === "coolest"
        ? colors.brass
        : colors.bronze;
  return {
    color,
    ramp: false,
    opacity: isSel ? 1 : 0.85,
    width: isSel ? 1.2 : 1.0,
    minPx: isSel ? 4.5 : 2.6,
    pulse: k === "coolest",
    order: isSel ? 12 : 10,
    lift: isSel ? 0.02 : 0,
  };
}

export function Routes({ result, view, selected, t, travellerAt }: Props) {
  const polys = useMemo(() => {
    if (!result) return null;
    const out: Partial<Record<RouteKey, RoutePolyline>> = {};
    for (const k of ORDER)
      if (result[k]?.segments?.length) out[k] = routePolyline(result[k]);
    return out;
  }, [result]);

  if (!result || !polys) return null;
  return (
    <group>
      {ORDER.map((k) => {
        const p = polys[k];
        const r = result[k];
        if (!p || !r) return null;
        const st = styleFor(k, view, selected);
        if (!st) return null;
        return (
          <RouteRibbon
            key={`${k}-${view}`}
            route={r}
            poly={p}
            style={st}
            t={t}
          />
        );
      })}
      {travellerAt != null && polys[selected] ? (
        <Traveller poly={polys[selected]!} at={travellerAt} />
      ) : null}
    </group>
  );
}

function Traveller({ poly, at }: { poly: RoutePolyline; at: number }) {
  const ref = useRef<Mesh>(null);
  const ring = useRef<Mesh>(null);
  useFrame(({ camera }) => {
    const p = pointAt(poly, at * poly.length);
    const d = Math.hypot(
      camera.position.x - p.x,
      camera.position.y - 1,
      camera.position.z - p.z,
    );
    const s = Math.max(0.8, d * 0.0035);
    if (ref.current) {
      ref.current.position.set(p.x, 0.9 * s + SCENE.routeY, p.z);
      ref.current.scale.setScalar(s);
    }
    if (ring.current) {
      ring.current.position.set(p.x, SCENE.routeY + 0.05 + d * 0.0004, p.z);
      ring.current.scale.setScalar(s);
    }
  });
  return (
    <>
      <mesh ref={ref} renderOrder={20}>
        <sphereGeometry args={[0.9, 20, 14]} />
        <meshStandardMaterial
          color={colors.champagne}
          emissive={colors.ember}
          emissiveIntensity={0.6}
          roughness={0.5}
        />
      </mesh>
      <mesh ref={ring} rotation-x={-Math.PI / 2} renderOrder={20}>
        <ringGeometry args={[1.5, 1.9, 40]} />
        <meshBasicMaterial
          color={colors.champagne}
          transparent
          opacity={0.8}
          depthWrite={false}
        />
      </mesh>
    </>
  );
}
