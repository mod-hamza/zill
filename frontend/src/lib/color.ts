// Perceptual colour helpers (OKLab) for the exposure ramp (PRD 12.3).
import { colors, exposureRamp } from "@/design/tokens";

export type RGB = [number, number, number]; // linear-light 0..1

export function hexToSrgb(hex: string): RGB {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as RGB;
}

const toLin = (c: number) =>
  c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
const toSrgb = (c: number) =>
  c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;

export function hexToLinear(hex: string): RGB {
  return hexToSrgb(hex).map(toLin) as RGB;
}

export function linearToHex(rgb: RGB): string {
  return (
    "#" +
    rgb
      .map((c) =>
        Math.round(Math.min(1, Math.max(0, toSrgb(c))) * 255)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}

export function linearToOklab([r, g, b]: RGB): RGB {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

export function oklabToLinear([L, a, b]: RGB): RGB {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

export function mixOklab(a: string, b: string, t: number): RGB {
  const A = linearToOklab(hexToLinear(a));
  const B = linearToOklab(hexToLinear(b));
  return oklabToLinear([
    A[0] + (B[0] - A[0]) * t,
    A[1] + (B[1] - A[1]) * t,
    A[2] + (B[2] - A[2]) * t,
  ]);
}

/** Exposure ramp shade -> #6F6A55 -> ember, perceptual. `x` in [0,1] = sun fraction. Linear RGB. */
export function exposureColor(x: number): RGB {
  const t = Math.min(1, Math.max(0, x));
  const stops = exposureRamp;
  for (let i = 0; i < stops.length - 1; i++) {
    const s0 = stops[i]!;
    const s1 = stops[i + 1]!;
    if (t <= s1.at)
      return mixOklab(s0.color, s1.color, (t - s0.at) / (s1.at - s0.at));
  }
  return hexToLinear(colors.ember);
}
