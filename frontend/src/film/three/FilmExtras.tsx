"use client";
// Film-only 3D layers, all driven by the current FrameState (no timers):
//   HairlineGrid (Ch.4), RoadDraw (Ch.4 brass hairlines drawn radially from the Burj),
//   SunArc (Ch.3 brass sun-path hairline + 12:00 / 16:00 marks), SunRays (Ch.5 thin warm lines
//   along the true sun direction), Travellers, EdgeLabels (Ch.5 real per-edge sun values), Globe.
import { Html } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  DoubleSide,
  Group,
  LineBasicMaterial,
  Line as ThreeLine,
  LineSegments,
  Mesh,
  ShaderMaterial,
  UniformsLib,
  UniformsUtils,
  Vector3,
} from "three";
import { colors } from "@/design/tokens";
import { buildRibbons, type RibbonLine } from "@/lib/graph";
import { pointAt } from "@/lib/routeGeom";
import { sunAt, minutesToHHMM } from "@/lib/sun";
import { useCity } from "@/state/city";
import { useSun } from "@/state/sun";
import { RIBBON_VERTEX, ribbonGeometry } from "@/three/ribbon";
import { SCENE } from "@/three/sceneConfig";
import { segMid, useFilmData } from "../data";
import { useFilm } from "../store";
import type { FrameState, OverlayItem } from "../types";
import { Globe } from "./Globe";

const cur = () => useFilm.getState().frame;

function overlay<K extends OverlayItem["kind"]>(
  f: FrameState | null,
  kind: K,
): Extract<OverlayItem, { kind: K }> | undefined {
  return f?.overlays.find((o) => o.kind === kind) as Extract<OverlayItem, { kind: K }> | undefined;
}

// ---------------------------------------------------------------------------------------------
function HairlineGrid() {
  const mat = useMemo(
    () =>
      new ShaderMaterial({
        uniforms: {
          uOpacity: { value: 0 },
          uColor: { value: new Color(colors.sand) },
        },
        vertexShader: /* glsl */ `
          varying vec3 vW;
          void main(){ vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`,
        fragmentShader: /* glsl */ `
          varying vec3 vW;
          uniform float uOpacity;
          uniform vec3 uColor;
          float gridLine(vec2 p, float step){
            vec2 g = abs(fract(p / step - 0.5) - 0.5) / fwidth(p / step);
            return 1.0 - min(min(g.x, g.y), 1.0);
          }
          void main(){
            float l = gridLine(vW.xz, 100.0) * 0.55 + gridLine(vW.xz, 500.0) * 0.45;
            float r = length(vW.xz);
            float fade = 1.0 - smoothstep(900.0, 2600.0, r);
            gl_FragColor = vec4(uColor, l * fade * uOpacity * 0.32);
          }`,
        transparent: true,
        depthWrite: false,
        side: DoubleSide,
        extensions: { derivatives: true } as never,
      }),
    [],
  );
  const ref = useRef<Mesh>(null);
  useFrame(() => {
    const g = cur()?.build.grid ?? 0;
    mat.uniforms.uOpacity!.value = g;
    if (ref.current) ref.current.visible = g > 0.001;
  });
  return (
    <mesh ref={ref} rotation-x={-Math.PI / 2} position={[0, 0.25, 0]} material={mat} renderOrder={3}>
      <planeGeometry args={[6000, 6000]} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------------------------
const roadFrag = /* glsl */ `
varying float vSide;
varying float vDist;
varying float vValue;
varying vec3 vWorld;
uniform float uDrawR;
uniform float uOpacity;
uniform vec3 uColor;
void main() {
  float r = length(vWorld.xz);
  if (r > uDrawR) discard;
  float head = smoothstep(uDrawR, uDrawR - 140.0, r);
  float s = abs(vSide);
  float a = (1.0 - smoothstep(0.55, 1.0, s)) * uOpacity * (0.45 + 0.55 * (1.0 - head));
  vec3 c = uColor * (1.0 + 1.4 * (1.0 - head));
  gl_FragColor = vec4(c, a);
}
`;

function RoadDraw() {
  const graph = useCity((s) => s.graph);
  const size = useThree((s) => s.size);
  const mat = useMemo(
    () =>
      new ShaderMaterial({
        uniforms: UniformsUtils.merge([
          UniformsLib.fog,
          {
            uLiftPerM: { value: 0.0003 },
            uWidthScale: { value: 1 },
            uMinPx: { value: 1.25 },
            uViewportH: { value: 1080 },
            uDrawR: { value: 0 },
            uOpacity: { value: 0 },
            uColor: { value: new Color(colors.brass) },
          },
        ]),
        vertexShader: RIBBON_VERTEX,
        fragmentShader: roadFrag,
        transparent: true,
        depthWrite: false,
        side: DoubleSide,
      }),
    [],
  );
  useEffect(() => {
    mat.uniforms.uViewportH!.value = size.height;
  }, [size.height, mat]);
  const geometry = useMemo(() => {
    if (!graph) return null;
    const e = graph.raw.edges;
    const lines: RibbonLine[] = [];
    for (let i = 0; i < e.u.length; i++) {
      const g = e.geom[i];
      if (!g || g.length < 4) continue;
      lines.push({ pts: g, width: 1.4 });
    }
    return ribbonGeometry(buildRibbons(lines, SCENE.roadY + 0.2));
  }, [graph]);
  const ref = useRef<Mesh>(null);
  useFrame(() => {
    const f = cur();
    const roads = f?.build.roads ?? 0;
    const grid = f?.build.grid ?? 0;
    const op = roads > 0 ? Math.min(1, grid * 1.4 + 0.15) * 0.85 : 0;
    mat.uniforms.uDrawR!.value = roads * 2600;
    mat.uniforms.uOpacity!.value = op;
    if (ref.current) ref.current.visible = op > 0.001;
  });
  if (!geometry) return null;
  return <mesh ref={ref} geometry={geometry} material={mat} frustumCulled={false} renderOrder={4} />;
}

// ---------------------------------------------------------------------------------------------
export const ARC_R = 880;
export const ARC_C: [number, number, number] = [0, 0, 0];

function arcPoint(dateIso: string, minutes: number, lat: number, lon: number) {
  const v = sunAt(dateIso, minutes, lat, lon).vector;
  return new Vector3(ARC_C[0] + v[0] * ARC_R, ARC_C[1] + v[1] * ARC_R, ARC_C[2] + v[2] * ARC_R);
}

function SunArc() {
  const dateIso = useSun((s) => s.dateIso);
  const origin = useSun((s) => s.origin);
  const { line, mat } = useMemo(() => {
    const pts: Vector3[] = [];
    for (let m = 4 * 60; m <= 21 * 60; m += 4) {
      const v = sunAt(dateIso, m, origin.lat, origin.lon);
      if (v.altDeg < -1) continue;
      pts.push(arcPoint(dateIso, m, origin.lat, origin.lon));
    }
    const g = new BufferGeometry().setFromPoints(pts);
    const mat = new LineBasicMaterial({
      color: colors.brass,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      fog: false,
    });
    return { line: new ThreeLine(g, mat), mat };
  }, [dateIso, origin.lat, origin.lon]);
  useEffect(() => () => line.geometry.dispose(), [line]);
  const dot = useRef<Mesh>(null);
  const grp = useRef<Group>(null);
  useFrame(({ camera }) => {
    const f = cur();
    const a = f?.sunArc ?? 0;
    mat.opacity = a * 0.85;
    if (grp.current) grp.current.visible = a > 0.001;
    if (dot.current) {
      const p = arcPoint(dateIso, useSun.getState().minutes, origin.lat, origin.lon);
      dot.current.position.copy(p);
      dot.current.scale.setScalar(camera.position.distanceTo(p) * 0.0042);
      (dot.current.material as LineBasicMaterial).opacity = a;
    }
  });
  const marks = ["12:00", "16:00"];
  return (
    <group ref={grp}>
      <primitive object={line} renderOrder={30} />
      <mesh ref={dot} renderOrder={31}>
        <sphereGeometry args={[1, 16, 12]} />
        <meshBasicMaterial color={colors.champagne} transparent depthWrite={false} fog={false} toneMapped={false} />
      </mesh>
      {marks.map((h) => {
        const [hh, mm] = h.split(":").map(Number);
        const p = arcPoint(dateIso, hh! * 60 + mm!, origin.lat, origin.lon);
        return <ArcMark key={h} hhmm={h} p={p} />;
      })}
      <ArcNow dateIso={dateIso} />
    </group>
  );
}

function ArcMark({ hhmm, p }: { hhmm: string; p: Vector3 }) {
  const ref = useRef<HTMLDivElement>(null);
  useFrame(() => {
    const f = cur();
    const o = overlay(f, "arclabels");
    const m = o?.marks.find((x) => x.hhmm === hhmm);
    if (ref.current) ref.current.style.opacity = String((o?.opacity ?? 0) * (m?.opacity ?? 0));
  });
  return (
    <Html position={[p.x, p.y, p.z]} center zIndexRange={[15, 0]} style={{ pointerEvents: "none" }}>
      <div ref={ref} className="film-arcmark" style={{ opacity: 0 }}>
        <span className="film-arcmark-tick" />
        <span className="font-display">{hhmm}</span>
      </div>
    </Html>
  );
}

function ArcNow({ dateIso }: { dateIso: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const grp = useRef<Group>(null);
  const origin = useSun((s) => s.origin);
  useFrame(() => {
    const f = cur();
    const o = overlay(f, "arclabels");
    const m = useSun.getState().minutes;
    const p = arcPoint(dateIso, m, origin.lat, origin.lon);
    grp.current?.position.copy(p);
    if (ref.current) {
      // hide the moving time label when it sits on a 12:00 / 16:00 mark
      const nearMark = Math.min(Math.abs(m - 720), Math.abs(m - 960)) < 8;
      ref.current.style.opacity = String((o?.opacity ?? 0) * (nearMark ? 0 : 1));
      const txt = minutesToHHMM(m, ":");
      if (ref.current.textContent !== txt) ref.current.textContent = txt;
    }
  });
  return (
    <group ref={grp}>
      <Html center zIndexRange={[16, 0]} style={{ pointerEvents: "none" }}>
        <div ref={ref} className="film-arcnow tabular" style={{ opacity: 0 }} />
      </Html>
    </group>
  );
}

// ---------------------------------------------------------------------------------------------
const RAY_N = 44;
function SunRays() {
  const { geom, mat } = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new BufferAttribute(new Float32Array(RAY_N * 2 * 3), 3));
    g.setAttribute("aT", new BufferAttribute(new Float32Array(RAY_N * 2).map((_, i) => i % 2), 1));
    const m = new ShaderMaterial({
      uniforms: { uOpacity: { value: 0 }, uColor: { value: new Color(colors.champagne) } },
      vertexShader: /* glsl */ `attribute float aT; varying float vT;
        void main(){ vT = aT; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: /* glsl */ `varying float vT; uniform float uOpacity; uniform vec3 uColor;
        void main(){ float a = mix(0.9, 0.0, vT) * uOpacity; gl_FragColor = vec4(uColor * 1.3, a * 0.11); }`,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
    });
    return { geom: g, mat: m };
  }, []);
  const ref = useRef<LineSegments>(null);
  useFrame(() => {
    const f = cur();
    const a = f?.sunRays ?? 0;
    mat.uniforms.uOpacity!.value = a;
    if (ref.current) ref.current.visible = a > 0.001;
    if (a <= 0.001) return;
    const v = useSun.getState().sun.vector;
    const pos = geom.getAttribute("position") as BufferAttribute;
    // a sweeping comb of rays across the towers (deterministic in localS)
    const sweep = ((f?.localS ?? 0) * 9) % 900;
    const hx = -v[2];
    const hz = v[0];
    const hn = Math.hypot(hx, hz) || 1;
    for (let i = 0; i < RAY_N; i++) {
      const k = (i * 0.618034) % 1;
      const across = (i / RAY_N - 0.5) * 1700;
      const along = ((k * 900 + sweep) % 900) - 450;
      const x = (hx / hn) * across - v[0] * along * 0.3;
      const z = (hz / hn) * across - v[2] * along * 0.3;
      const y = 40 + ((i * 37) % 11) * 32;
      const L = 2400;
      pos.setXYZ(i * 2, x, y, z);
      pos.setXYZ(i * 2 + 1, x + v[0] * L, y + v[1] * L, z + v[2] * L);
    }
    pos.needsUpdate = true;
    geom.computeBoundingSphere();
  });
  return <lineSegments ref={ref} geometry={geom} material={mat} frustumCulled={false} renderOrder={40} />;
}

// ---------------------------------------------------------------------------------------------
/** traveller groups [0] fastest/first, [1] coolest/second — the split view toggles them per pass */
export const travellerGroups: (Group | null)[] = [null, null];

function Travellers() {
  const data = useFilmData((s) => s.data);
  const refs = useRef<(Group | null)[]>([]);
  useFrame(({ camera }) => {
    const f = cur();
    const list = f?.travellers ?? [];
    for (let i = 0; i < 2; i++) {
      const g = refs.current[i];
      if (!g) continue;
      const tr = list[i];
      if (!tr || !data) {
        g.visible = false;
        continue;
      }
      const geo = data.scenarioGeo[tr.scenario]?.[tr.key === "fastest" ? "fastest" : "coolest"];
      if (!geo) {
        g.visible = false;
        continue;
      }
      g.visible = true;
      const p = pointAt(geo.poly, tr.at * geo.poly.length);
      const d = Math.hypot(camera.position.x - p.x, camera.position.y - 1, camera.position.z - p.z);
      const s = Math.max(0.55, d * 0.0042);
      g.position.set(p.x, SCENE.routeY + d * 0.0004, p.z);
      g.scale.setScalar(s);
      const body = g.children[0] as Mesh;
      const m = body.material as unknown as { color: Color; emissive: Color };
      m.color.set(colors.champagne);
      m.emissive.set(tr.color);
    }
  });
  return (
    <>
      {[0, 1].map((i) => (
        <group
          key={i}
          ref={(g) => {
            refs.current[i] = g;
            travellerGroups[i] = g;
          }}
          visible={false}
        >
          <mesh position={[0, 0.95, 0]} renderOrder={22}>
            <sphereGeometry args={[0.8, 20, 14]} />
            <meshStandardMaterial roughness={0.45} emissiveIntensity={0.55} />
          </mesh>
          <mesh rotation-x={-Math.PI / 2} position={[0, 0.06, 0]} renderOrder={22}>
            <ringGeometry args={[1.4, 1.75, 40]} />
            <meshBasicMaterial color={colors.champagne} transparent opacity={0.85} depthWrite={false} />
          </mesh>
        </group>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------------------------
function EdgeLabels() {
  const data = useFilmData((s) => s.data);
  const wrap = useRef<HTMLDivElement[]>([]);
  useFrame(() => {
    const o = overlay(cur(), "edgelabels");
    for (const el of wrap.current) if (el) el.style.opacity = String(o?.opacity ?? 0);
  });
  if (!data) return null;
  const route = data.hero.coolest;
  const dep = data.hero.depart.split(":").map(Number);
  const depMin = (dep[0] ?? 0) * 60 + (dep[1] ?? 0);
  return (
    <>
      {data.labelSegs.map((k, i) => {
        const s = route.segments[k];
        if (!s) return null;
        const [x, z] = segMid(s.geometry);
        const at = minutesToHHMM(depMin + s.arrival_s / 60, ":");
        return (
          <Html key={k} position={[x, 2, z]} zIndexRange={[14, 0]} style={{ pointerEvents: "none" }}>
            <div ref={(el) => { if (el) wrap.current[i] = el; }} className="film-edgelabel" style={{ opacity: 0 }}>
              <span className="film-edgelabel-stem" />
              <span className="film-edgelabel-box">
                <b className="tabular" style={{ color: s.sun > 0.5 ? colors.ember : s.sun < 0.2 ? colors.oasis : colors.sand }}>
                  {Math.round(s.sun * 100)}%
                </b>{" "}
                in sun <em className="tabular">at {at}</em>
              </span>
            </div>
          </Html>
        );
      })}
    </>
  );
}

export function FilmExtras() {
  return (
    <>
      <HairlineGrid />
      <RoadDraw />
      <SunArc />
      <SunRays />
      <Travellers />
      <EdgeLabels />
      <Globe />
    </>
  );
}
