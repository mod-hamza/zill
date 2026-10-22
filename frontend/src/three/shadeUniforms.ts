// Shared uniforms + GLSL for everything that sits on the ground and must agree with the shade
// raster (ground plane, road ribbons). One canvas -> one module-level uniform set.
import {
  Color,
  DataTexture,
  LinearFilter,
  RedFormat,
  Texture,
  UnsignedByteType,
  Vector2,
  Vector3,
} from "three";

function blankTexture(): Texture {
  const t = new DataTexture(
    new Uint8Array([255]),
    1,
    1,
    RedFormat,
    UnsignedByteType,
  );
  t.magFilter = LinearFilter;
  t.minFilter = LinearFilter;
  t.needsUpdate = true;
  return t;
}

export const shadeUniforms = {
  uShadeA: { value: blankTexture() as Texture },
  uShadeB: { value: blankTexture() as Texture },
  uShadeMix: { value: 0 },
  /** 0 while no raster is loaded (soft fade-in, no pop), 1 when shown */
  uShadeOpacity: { value: 0 },
  uGridOrigin: { value: new Vector2(-1000, -1000) },
  uGridSize: { value: new Vector2(2000, 2000) },
  uTexel: { value: new Vector2(1 / 1000, 1 / 1000) },
  uGroundSun: { value: new Color(0.5, 0.45, 0.38) },
  uGroundShade: { value: new Color(0.05, 0.08, 0.09) },
  uSunDir: { value: new Vector3(0, 1, 0) },
  /** ground beyond the modelled area: a quiet plinth that fades into the haze */
  uOutside: { value: new Color(0.06, 0.05, 0.045) },
};

/** GLSL: `float zillSunFrac(vec2 xz, out float inside)` + `vec3 zillGround(vec2 xz)`. */
export const SHADE_GLSL = /* glsl */ `
uniform sampler2D uShadeA;
uniform sampler2D uShadeB;
uniform float uShadeMix;
uniform float uShadeOpacity;
uniform vec2 uGridOrigin;
uniform vec2 uGridSize;
uniform vec2 uTexel;
uniform vec3 uGroundSun;
uniform vec3 uGroundShade;
uniform vec3 uOutside;

float zillTap(sampler2D t, vec2 uv) {
  // 5-tap soft sample (~1 texel): slightly softened shadow edges, PRD 13.1.3
  float c = texture2D(t, uv).r * 0.36;
  c += texture2D(t, uv + vec2(uTexel.x, 0.0)).r * 0.16;
  c += texture2D(t, uv - vec2(uTexel.x, 0.0)).r * 0.16;
  c += texture2D(t, uv + vec2(0.0, uTexel.y)).r * 0.16;
  c += texture2D(t, uv - vec2(0.0, uTexel.y)).r * 0.16;
  return c;
}

// CONTRACTS 2: u = (x - x0) / W, v = (z - z0) / H, texture flipY = false, PNG row 0 = north.
float zillSunFrac(vec2 xz, out float inside) {
  vec2 uv = (xz - uGridOrigin) / uGridSize;
  vec2 e = min(uv, 1.0 - uv);
  inside = smoothstep(0.0, 0.012, min(e.x, e.y));
  float a = zillTap(uShadeA, uv);
  float b = zillTap(uShadeB, uv);
  return mix(a, b, uShadeMix);
}

vec3 zillGround(vec2 xz) {
  float inside;
  float f = zillSunFrac(xz, inside);
  // sun fraction -> colour: perceptual-ish (mix in sqrt space keeps mid-tones from going muddy)
  vec3 lit = mix(sqrt(uGroundShade), sqrt(uGroundSun), smoothstep(0.0, 1.0, f));
  lit *= lit;
  // while no raster is loaded show a neutral mid tone (soft fade, no pop)
  vec3 neutral = mix(uGroundShade, uGroundSun, 0.55);
  vec3 c = mix(neutral, lit, uShadeOpacity);
  return mix(uOutside, c, inside);
}
`;
