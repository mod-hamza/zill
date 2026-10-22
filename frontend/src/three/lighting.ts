// Time-of-day lighting & grading model (PRD 12.5). Pure: (sun altitude, azimuth) -> parameters.
// Colours are keyframed by altitude and interpolated in OKLab. Everything warm & restrained:
// dusty desert sky (never electric blue), bleached noon, amber golden hour, blue-umber dusk.
import {
  hexToLinear,
  linearToOklab,
  oklabToLinear,
  type RGB,
} from "@/lib/color";
import { colors } from "@/design/tokens";

type Key = {
  alt: number;
  zenith: string;
  horizon: string;
  sunColor: string;
  sunIntensity: number;
  hemiSky: string;
  hemiGround: string;
  hemiIntensity: number;
  fog: string;
  fogDensity: number;
  /** 0..1 how "dusk" it is: drives tungsten windows */
  dusk: number;
  /** grade: tint multiplier, saturation, contrast, exposure (stops) */
  tint: string;
  saturation: number;
  contrast: number;
  exposure: number;
};

// Afternoon/evening keys (morning keys below are derived with a rose-gold shift).
const KEYS: Key[] = [
  {
    alt: -14,
    zenith: "#07080B",
    horizon: "#15161B",
    sunColor: "#000000",
    sunIntensity: 0,
    hemiSky: "#2B3140",
    hemiGround: "#0E0C0A",
    hemiIntensity: 0.16,
    fog: "#101115",
    fogDensity: 0.00012,
    dusk: 1,
    tint: "#D3D6E2",
    saturation: 0.8,
    contrast: 1.04,
    exposure: 0.0,
  },
  {
    alt: -5,
    zenith: "#141A28",
    horizon: "#4A3530",
    sunColor: "#000000",
    sunIntensity: 0,
    hemiSky: "#3A4157",
    hemiGround: "#1A1511",
    hemiIntensity: 0.3,
    fog: "#2A2428",
    fogDensity: 0.00012,
    dusk: 1,
    tint: "#E2D8DC",
    saturation: 0.85,
    contrast: 1.05,
    exposure: 0.1,
  },
  {
    alt: 1.5,
    zenith: "#2A3449",
    horizon: "#B07A58",
    sunColor: "#FF9A5C",
    sunIntensity: 1.1,
    hemiSky: "#5A5C70",
    hemiGround: "#2A231C",
    hemiIntensity: 0.4,
    fog: "#6E5546",
    fogDensity: 0.00011,
    dusk: 0.6,
    tint: "#FFE2C8",
    saturation: 0.95,
    contrast: 1.05,
    exposure: 0.05,
  },
  {
    alt: 8,
    zenith: "#46597A",
    horizon: "#D0A27C",
    sunColor: "#FFC08A",
    sunIntensity: 2.2,
    hemiSky: "#7C8494",
    hemiGround: "#5E4C3A",
    hemiIntensity: 0.7,
    fog: "#A58C76",
    fogDensity: 0.0001,
    dusk: 0,
    tint: "#FFEBD6",
    saturation: 0.95,
    contrast: 1.07,
    exposure: 0.0,
  },
  {
    alt: 22,
    zenith: "#5F7690",
    horizon: "#D3C3A8",
    sunColor: "#FFE1C0",
    sunIntensity: 2.6,
    hemiSky: "#93A3B2",
    hemiGround: "#857660",
    hemiIntensity: 0.95,
    fog: "#B4A894",
    fogDensity: 0.0001,
    dusk: 0,
    tint: "#FFF5EA",
    saturation: 0.9,
    contrast: 1.08,
    exposure: 0.0,
  },
  {
    alt: 60,
    zenith: "#7088A0",
    horizon: "#DDD4C2",
    sunColor: "#FFF4E6",
    sunIntensity: 2.8,
    hemiSky: "#A3B1BC",
    hemiGround: "#8E806A",
    hemiIntensity: 1.05,
    fog: "#C2BAA9",
    fogDensity: 0.0001,
    dusk: 0,
    tint: "#FFF9F2",
    saturation: 0.86,
    contrast: 1.1,
    exposure: 0.0,
  },
];

// Morning shift: rose-gold/low blue (PRD 12.5 dawn) — applied to low-altitude keys only.
const DAWN_TINT = "#FFD3C4";
const DAWN_HORIZON = "#C98F7E";

export type Lighting = {
  zenith: RGB;
  horizon: RGB;
  sunColor: RGB;
  sunIntensity: number;
  hemiSky: RGB;
  hemiGround: RGB;
  hemiIntensity: number;
  fog: RGB;
  fogDensity: number;
  dusk: number;
  tint: RGB;
  saturation: number;
  contrast: number;
  exposure: number;
  /** final ground colours for the shade overlay (linear, pre-tone-mapping) */
  groundSun: RGB;
  groundShade: RGB;
  /** sun disc brightness in the sky shader (HDR) */
  sunDisc: number;
};

const mix = (a: RGB, b: RGB, t: number): RGB => {
  const A = linearToOklab(a);
  const B = linearToOklab(b);
  return oklabToLinear([
    A[0] + (B[0] - A[0]) * t,
    A[1] + (B[1] - A[1]) * t,
    A[2] + (B[2] - A[2]) * t,
  ]);
};
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const scale = (c: RGB, k: number): RGB => [c[0] * k, c[1] * k, c[2] * k];
const mul = (a: RGB, b: RGB): RGB => [a[0] * b[0], a[1] * b[1], a[2] * b[2]];
const addc = (a: RGB, b: RGB): RGB => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];

// Ground albedo: warm pale paving (sand token darkened to a plausible ~0.35 albedo).
const GROUND_ALBEDO = scale(hexToLinear(colors.sand), 0.36);
const SHADE = hexToLinear(colors.shade);

export function lightingFor(altDeg: number, azDeg: number): Lighting {
  const alt = Math.max(
    KEYS[0]!.alt,
    Math.min(KEYS[KEYS.length - 1]!.alt, altDeg),
  );
  let i = 0;
  while (i < KEYS.length - 2 && alt > KEYS[i + 1]!.alt) i++;
  const k0 = KEYS[i]!;
  const k1 = KEYS[i + 1]!;
  const t = (alt - k0.alt) / (k1.alt - k0.alt);
  const c = (f: (k: Key) => string) =>
    mix(hexToLinear(f(k0)), hexToLinear(f(k1)), t);
  const n = (f: (k: Key) => number) => lerp(f(k0), f(k1), t);

  const morning = azDeg < 180;
  // how strongly the dawn shift applies: full near the horizon, gone by ~18 deg
  const dawnW = morning
    ? Math.max(0, Math.min(1, (18 - altDeg) / 16)) *
      Math.max(0, Math.min(1, (altDeg + 10) / 8))
    : 0;

  let horizon = c((k) => k.horizon);
  let tint = c((k) => k.tint);
  if (dawnW > 0) {
    horizon = mix(horizon, hexToLinear(DAWN_HORIZON), dawnW * 0.55);
    tint = mix(tint, hexToLinear(DAWN_TINT), dawnW * 0.6);
  }

  const sunColor = c((k) => k.sunColor);
  const sunIntensity = n((k) => k.sunIntensity);
  const hemiSky = c((k) => k.hemiSky);
  const hemiIntensity = n((k) => k.hemiIntensity);
  const sinAlt = Math.max(0, Math.sin((altDeg * Math.PI) / 180));

  const ambient = scale(hemiSky, hemiIntensity);
  const direct = scale(sunColor, sunIntensity * sinAlt);
  const groundSun = mul(GROUND_ALBEDO, addc(ambient, direct));
  // shaded ground: the brand's deep teal-slate, lifted by sky light so it is never pure black
  // shaded ground reads as the brand's deep teal-slate (PRD 12.3 `shade`), lifted by sky light
  const skyLift = Math.max(0.3, hemiIntensity * 0.95);
  const groundShade = mix(
    mul(GROUND_ALBEDO, ambient),
    scale(SHADE, skyLift),
    0.78,
  );

  return {
    zenith: c((k) => k.zenith),
    horizon,
    sunColor,
    sunIntensity,
    hemiSky,
    hemiGround: c((k) => k.hemiGround),
    hemiIntensity,
    fog: c((k) => k.fog),
    fogDensity: n((k) => k.fogDensity),
    dusk: n((k) => k.dusk),
    tint,
    saturation: n((k) => k.saturation),
    contrast: n((k) => k.contrast),
    exposure: n((k) => k.exposure),
    groundSun,
    groundShade,
    sunDisc: altDeg > -1 ? 18 + 10 * Math.min(1, Math.max(0, altDeg / 30)) : 0,
  };
}
