// Ribbon geometry + shader plumbing shared by roads, links and routes.
import { BufferAttribute, BufferGeometry, Sphere, Vector3 } from "three";
import type { RibbonData } from "@/lib/graph";

export function ribbonGeometry(d: RibbonData): BufferGeometry {
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(d.center, 3));
  g.setAttribute("aOffset", new BufferAttribute(d.offset, 2));
  g.setAttribute("aSide", new BufferAttribute(d.side, 1));
  g.setAttribute("aDist", new BufferAttribute(d.dist, 1));
  g.setAttribute("aWidth", new BufferAttribute(d.width, 1));
  g.setAttribute("aValue", new BufferAttribute(d.value, 1));
  g.setIndex(new BufferAttribute(d.index, 1));
  g.computeBoundingSphere();
  if (g.boundingSphere)
    g.boundingSphere = new Sphere(
      g.boundingSphere.center,
      g.boundingSphere.radius + 50,
    );
  else g.boundingSphere = new Sphere(new Vector3(), 1e5);
  return g;
}

/**
 * Vertex shader body: expands the centre line by `aOffset * halfWidth` where halfWidth is the
 * metric width, but never thinner than `uMinPx` screen pixels (routes stay legible from altitude).
 */
export const RIBBON_VERTEX = /* glsl */ `
attribute vec2 aOffset;
attribute float aSide;
attribute float aDist;
attribute float aWidth;
attribute float aValue;
uniform float uWidthScale;
uniform float uMinPx;
uniform float uViewportH;
uniform float uLiftPerM;
varying float vSide;
varying float vDist;
varying float vValue;
varying vec3 vWorld;
#include <fog_pars_vertex>
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  float distCam = length(cameraPosition - wp.xyz);
  float mPerPx = 2.0 * distCam / (projectionMatrix[1][1] * uViewportH);
  float hw = max(aWidth * 0.5 * uWidthScale, uMinPx * mPerPx);
  wp.xz += aOffset * hw;
  // distance-proportional lift keeps ground-hugging layers above the ground in the depth buffer
  // (a few cm at street level, under a metre from 2 km away)
  wp.y += distCam * uLiftPerM;
  vSide = aSide;
  vDist = aDist;
  vValue = aValue;
  vWorld = wp.xyz;
  vec4 mvPosition = viewMatrix * wp;
  gl_Position = projectionMatrix * mvPosition;
  #include <fog_vertex>
}
`;
