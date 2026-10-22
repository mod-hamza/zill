// Custom grade pass (PRD 12.5): time-of-day "LUT-like" curves driven by uniforms, the interior
// AC-link cool shift, vignette and deterministic film grain (seeded by frame-t, never the clock).
import { BlendFunction, Effect } from "postprocessing";
import { Color, Uniform, Vector3 } from "three";

const fragment = /* glsl */ `
uniform vec3 uTint;
uniform float uSaturation;
uniform float uContrast;
uniform float uGain;
uniform float uIndoor;
uniform vec3 uIndoorTint;
uniform float uVignette;
uniform float uGrain;
uniform float uSeed;

float zg(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
  vec3 c = inputColor.rgb * uGain;
  // white-balance style tint (normalised so it does not change exposure)
  float tl = dot(uTint, vec3(0.2126, 0.7152, 0.0722));
  c *= uTint / max(tl, 1e-3);
  // interior / AC-link grade: cooler towards oasis, a little dimmer
  float il = dot(uIndoorTint, vec3(0.2126, 0.7152, 0.0722));
  vec3 itn = mix(vec3(1.0), uIndoorTint / max(il, 1e-3), 0.55);
  c = mix(c, c * itn * 0.8, uIndoor);
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = mix(vec3(l), c, uSaturation);
  // contrast around mid-grey in a perceptual (gamma) domain
  vec3 g = pow(max(c, 0.0), vec3(1.0 / 2.2));
  g = (g - 0.5) * uContrast + 0.5;
  // vignette
  vec2 d = (uv - 0.5) * vec2(1.0, 0.82);
  float v = smoothstep(0.28, 0.78, length(d));
  g *= 1.0 - uVignette * v;
  // fine grain, luminance weighted, deterministic per frame-t
  float n = zg(gl_FragCoord.xy + vec2(uSeed * 37.0, uSeed * 91.0)) - 0.5;
  g += n * uGrain * (0.35 + 0.65 * (1.0 - abs(dot(g, vec3(0.333)) - 0.5) * 2.0));
  c = pow(max(g, 0.0), vec3(2.2));
  outputColor = vec4(c, inputColor.a);
}
`;

export class GradeEffect extends Effect {
  constructor() {
    super("ZillGrade", fragment, {
      blendFunction: BlendFunction.NORMAL,
      uniforms: new Map<string, Uniform>([
        ["uTint", new Uniform(new Vector3(1, 1, 1))],
        ["uSaturation", new Uniform(1)],
        ["uContrast", new Uniform(1.06)],
        ["uGain", new Uniform(1)],
        ["uIndoor", new Uniform(0)],
        ["uIndoorTint", new Uniform(new Color("#5E8C7B"))],
        ["uVignette", new Uniform(0.25)],
        ["uGrain", new Uniform(0.04)],
        ["uSeed", new Uniform(0)],
      ]),
    });
  }
  set(name: string, value: unknown) {
    const u = this.uniforms.get(name);
    if (u) u.value = value;
  }
}
