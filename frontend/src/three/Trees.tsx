"use client";
// Instanced low-poly canopies from trees.json (muted sage/olive, no sway). One draw call.
import { useEffect, useMemo, useRef } from "react";
import {
  Color,
  IcosahedronGeometry,
  InstancedMesh,
  Matrix4,
  MeshStandardMaterial,
  Quaternion,
  Vector3,
} from "three";
import { useCity } from "@/state/city";
import { SCENE } from "./sceneConfig";

export function Trees() {
  const trees = useCity((s) => s.trees);
  const ref = useRef<InstancedMesh>(null);
  const geometry = useMemo(() => {
    const g = new IcosahedronGeometry(1, 1);
    g.computeVertexNormals();
    return g;
  }, []);
  const material = useMemo(
    () =>
      new MeshStandardMaterial({
        roughness: 0.95,
        metalness: 0,
        flatShading: true,
      }),
    [],
  );

  useEffect(() => {
    const mesh = ref.current;
    if (!mesh || !trees) return;
    const m = new Matrix4();
    const q = new Quaternion();
    const s = new Vector3();
    const p = new Vector3();
    const c = new Color();
    trees.forEach((t, i) => {
      const h = t.h || 7;
      const r = t.r || 3;
      // canopy body from ~35% of height to the top
      const ch = h * 0.65;
      p.set(t.x, h - ch / 2, t.z);
      const k = ((i * 2654435761) >>> 0) / 4294967295;
      q.setFromAxisAngle(new Vector3(0, 1, 0), k * Math.PI * 2);
      s.set(r * (0.92 + 0.16 * k), ch / 2, r * (0.92 + 0.16 * (1 - k)));
      m.compose(p, q, s);
      mesh.setMatrixAt(i, m);
      c.set(SCENE.canopy[i % SCENE.canopy.length]!);
      mesh.setColorAt(i, c);
    });
    mesh.count = trees.length;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    material.needsUpdate = true; // recompile with instance colours
    mesh.computeBoundingSphere();
  }, [trees, material]);

  if (!trees || trees.length === 0) return null;
  return (
    <instancedMesh
      ref={ref}
      args={[geometry, material, trees.length]}
      castShadow
      receiveShadow
      frustumCulled={false}
    />
  );
}
