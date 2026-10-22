"use client";
// Snapped A / B endpoint markers: a hairline ring on the ground + a small serif letter.
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group } from "three";
import { colors } from "@/design/tokens";
import type { Endpoint } from "@/state/route";
import { SCENE } from "./sceneConfig";

function Pin({ e, letter }: { e: Endpoint; letter: string }) {
  const g = useRef<Group>(null);
  useFrame(({ camera }) => {
    if (!g.current) return;
    const d = Math.hypot(
      camera.position.x - e.x,
      camera.position.y,
      camera.position.z - e.z,
    );
    g.current.scale.setScalar(Math.max(1, d * 0.004));
    g.current.position.y = d * 0.0004; // stay above the ground in the depth buffer
  });
  return (
    <group position={[e.x, SCENE.routeY + 0.04, e.z]}>
      <group ref={g}>
        <mesh rotation-x={-Math.PI / 2} renderOrder={21}>
          <ringGeometry args={[2.2, 2.6, 48]} />
          <meshBasicMaterial
            color={colors.champagne}
            transparent
            opacity={0.95}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
        <mesh rotation-x={-Math.PI / 2} renderOrder={21}>
          <circleGeometry args={[0.9, 24]} />
          <meshBasicMaterial
            color={colors.brass}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>
      <Html
        center
        position={[0, 0, 0]}
        zIndexRange={[20, 0]}
        style={{ pointerEvents: "none" }}
      >
        <div className="zill-pin">
          <span className="font-display">{letter}</span>
          {e.name ? <em>{e.name}</em> : null}
        </div>
      </Html>
    </group>
  );
}

export function Markers({ a, b }: { a: Endpoint | null; b: Endpoint | null }) {
  return (
    <>
      {a ? <Pin e={a} letter="A" /> : null}
      {b ? <Pin e={b} letter="B" /> : null}
    </>
  );
}
