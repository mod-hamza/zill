"use client";
// Ch.11: a dark matte globe. Only cities that are actually baked (/api/cities, status "ready")
// are filled brass points; the roadmap cities are hollow rings labelled "roadmap". The globe sits
// far above the city (see ch11 GLOBE_C); the Film dims sky/ground to ink while it is on screen.
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Color, Group, Quaternion, ShaderMaterial, Vector3 } from "three";
import { colors } from "@/design/tokens";
import { GLOBE_C, GLOBE_R } from "../chapters/ch11";
import { useFilmData } from "../data";
import { useFilm } from "../store";

const DEG = Math.PI / 180;
/** roadmap (NOT baked) — PRD 14.2 Ch.11 */
export const ROADMAP_CITIES = [
  { name: "Doha", lat: 25.29, lon: 51.53 },
  { name: "Riyadh", lat: 24.71, lon: 46.68 },
  { name: "Singapore", lat: 1.35, lon: 103.82 },
  { name: "Phoenix", lat: 33.45, lon: -112.07 },
];

/** label placement so neighbouring Gulf cities do not overlap */
const LABEL_SIDE: Record<string, string> = { Doha: "up", Riyadh: "left", Singapore: "right", Phoenix: "right" };

function onSphere(lat: number, lon: number, r: number): [number, number, number] {
  return [r * Math.cos(lat * DEG) * Math.sin(lon * DEG), r * Math.sin(lat * DEG), r * Math.cos(lat * DEG) * Math.cos(lon * DEG)];
}

export function Globe() {
  const data = useFilmData((s) => s.data);
  const grp = useRef<Group>(null);
  const spin = useRef<Group>(null);
  const labels = useRef<(HTMLDivElement | null)[]>([]);
  const mat = useMemo(
    () =>
      new ShaderMaterial({
        uniforms: {
          uBase: { value: new Color(colors.stone).multiplyScalar(2.4) },
          uRim: { value: new Color(colors.bronze) },
          uLight: { value: new Vector3(-0.5, 0.55, 0.65).normalize() },
          uOpacity: { value: 0 },
        },
        vertexShader: /* glsl */ `varying vec3 vN; varying vec3 vV;
          void main(){ vec4 w = modelMatrix * vec4(position,1.0); vN = normalize(mat3(modelMatrix) * normal);
            vV = normalize(cameraPosition - w.xyz); gl_Position = projectionMatrix * viewMatrix * w; }`,
        fragmentShader: /* glsl */ `varying vec3 vN; varying vec3 vV; uniform vec3 uBase; uniform vec3 uRim; uniform vec3 uLight; uniform float uOpacity;
          void main(){ float l = max(dot(normalize(vN), uLight), 0.0); float rim = pow(1.0 - max(dot(normalize(vN), vV), 0.0), 3.0);
            vec3 c = uBase * (0.22 + 0.78 * l) + uRim * rim * 0.16; gl_FragColor = vec4(c * uOpacity, 1.0); }`,
        transparent: false,
      }),
    [],
  );
  const lon0 = data?.meta.origin.lon ?? 55;
  const lat0 = data?.meta.origin.lat ?? 25;
  const baked = data?.bakedCities ?? [];
  const all = [
    ...baked.map((c) => ({ ...c, baked: true })),
    ...ROADMAP_CITIES.filter((r) => !baked.some((b) => b.name.includes(r.name))).map((c) => ({ ...c, baked: false })),
  ];
  const tmp = useMemo(() => new Vector3(), []);
  useFrame(({ camera }) => {
    const f = useFilm.getState().frame;
    const g = f?.globe ?? 0;
    if (grp.current) grp.current.visible = g > 0.001;
    mat.uniforms.uOpacity!.value = g;
    if (g <= 0.001) return;
    if (spin.current) spin.current.rotation.y = -lon0 * DEG + 0.12 - 0.25 * (f?.localT ?? 0);
    const o = f?.overlays.find((x) => x.kind === "globelabels")?.opacity ?? 0;
    all.forEach((c, i) => {
      const el = labels.current[i];
      if (!el || !spin.current) return;
      const p = onSphere(c.lat, c.lon, GLOBE_R);
      tmp.set(p[0], p[1], p[2]).applyMatrix4(spin.current.matrixWorld);
      const n = tmp.clone().sub(new Vector3(...GLOBE_C)).normalize();
      const v = camera.position.clone().sub(tmp).normalize();
      const facing = Math.max(0, Math.min(1, n.dot(v) * 4));
      el.style.opacity = String(o * facing);
    });
  });
  if (!data) return null;
  return (
    <group ref={grp} position={GLOBE_C} visible={false} rotation-x={(lat0 * 0.6) * DEG}>
      <group ref={spin}>
        <mesh material={mat} renderOrder={50}>
          <sphereGeometry args={[GLOBE_R, 96, 64]} />
        </mesh>
        {all.map((c, i) => {
          const p = onSphere(c.lat, c.lon, GLOBE_R * 1.003);
          const out = new Vector3(...p).normalize();
          const q = new Quaternion().setFromUnitVectors(new Vector3(0, 0, 1), out);
          const side = LABEL_SIDE[c.name] ?? "right";
          return (
            <group key={c.name} position={p}>
              {c.baked ? (
                <mesh renderOrder={51}>
                  <sphereGeometry args={[38, 16, 12]} />
                  <meshBasicMaterial color={colors.brass} toneMapped={false} />
                </mesh>
              ) : (
                <mesh renderOrder={51} quaternion={q}>
                  <ringGeometry args={[34, 46, 40]} />
                  <meshBasicMaterial color={colors.sand} transparent opacity={0.85} />
                </mesh>
              )}
              <Html zIndexRange={[12, 0]} style={{ pointerEvents: "none" }}>
                <div
                  ref={(el) => {
                    labels.current[i] = el;
                  }}
                  className={`film-globelabel is-${side}`}
                  style={{ opacity: 0, color: c.baked ? colors.brass : colors.sand }}
                >
                  {c.name}
                  <em>{c.baked ? "baked" : "roadmap"}</em>
                </div>
              </Html>
            </group>
          );
        })}
      </group>
    </group>
  );
}
