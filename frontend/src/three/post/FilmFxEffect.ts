// Film-only post effect (FILM stream, additive). Identity unless the Film drives its uniforms:
//   uShimmer  Ch.2 heat shimmer: a very subtle screen-space distortion on the far ground only
//             (a band just below the horizon line `uHorizonY`), animated by the Film's frame-t.
//   uSplit    Ch.6 split view: the right half shows a second camera rendered into `uSplitTex`
//             (linear HDR, same scene, same clock) — tone mapping/grade still happen afterwards.
import { BlendFunction, Effect } from "postprocessing";
import { Texture, Uniform } from "three";

const fragment = /* glsl */ `
uniform float uShimmer;
uniform float uHorizonY;
uniform float uTime;
uniform float uSplit;
uniform sampler2D uSplitTex;

void mainUv(inout vec2 uv) {
  if (uShimmer > 0.0) {
    // only below the horizon, strongest just under it, gone 25% of the screen further down
    float below = uHorizonY - uv.y;
    float band = smoothstep(0.0, 0.03, below) * (1.0 - smoothstep(0.06, 0.26, below));
    float w = sin(uv.y * 410.0 + uTime * 7.3) * 0.6 + sin(uv.y * 173.0 - uTime * 4.1 + uv.x * 23.0) * 0.4;
    uv.x += w * band * uShimmer * 0.0011;
    uv.y += sin(uv.x * 90.0 + uTime * 3.1) * band * uShimmer * 0.0005;
  }
}

void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
  vec4 c = inputColor;
  if (uSplit > 0.0 && uv.x > 1.0 - 0.5 * uSplit) {
    c = vec4(texture2D(uSplitTex, uv).rgb, inputColor.a);
  }
  outputColor = c;
}
`;

export class FilmFxEffect extends Effect {
  constructor() {
    super("ZillFilmFx", fragment, {
      blendFunction: BlendFunction.NORMAL,
      uniforms: new Map<string, Uniform>([
        ["uShimmer", new Uniform(0)],
        ["uHorizonY", new Uniform(0.5)],
        ["uTime", new Uniform(0)],
        ["uSplit", new Uniform(0)],
        ["uSplitTex", new Uniform(null as Texture | null)],
      ]),
    });
  }
  set(name: string, value: unknown) {
    const u = this.uniforms.get(name);
    if (u) u.value = value;
  }
}

/** The one instance (one canvas). The Film writes its uniforms; Post.tsx mounts it. */
export const filmFx = new FilmFxEffect();
