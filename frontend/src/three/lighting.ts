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

/**
 * Sun altitude at local solar noon (deg) for an ISO date and latitude: 90 - |lat - declination|,
 * declination from the standard day-of-year approximation (±0.5°, plenty for a colour grade).
 */
export function noonAltitudeDeg(latDeg: number, dateIso: string): number {
  const d = new Date(`${dateIso.slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return 90;
  const n = Math.floor((d.getTime() - Date.UTC(d.getUTCFullYear(), 0, 0)) / 86_400_000);
  const decl = 23.44 * Math.sin((2 * Math.PI * (284 + n)) / 365);
  return 90 - Math.abs(latDeg - decl);
}

// Low-sun day grade (generic, by the day's own sun height — never by city): when the sun's
// highest point of the day is low (high-latitude winter), a 6–10° sun at midday is thin, pale
// daylight, not a golden hour. Shift towards a cool, pale, slightly desaturated look, inside the
// palette (slate / ivory greys; no blue neon). Sunrise/sunset on such days keep their warmth.
const LOW_DAY = {
  /** the grade is full when the day's noon altitude is <= full, gone when >= none (deg) */
  full: 10,
  none: 26,
  sun: "#F4E6D2",
  horizon: "#CDCBC4",
  zenith: "#6E8092",
  fog: "#B8BAB6",
  hemiSky: "#98A3AC",
  hemiGround: "#57534D",
  tint: "#EFF0EE",
} as const;

/** 0..1 weight of the low-sun day grade for a sun at altDeg on a day whose noon altitude is noonAltDeg */
export function lowSunWeight(altDeg: number, noonAltDeg: number): number {
  const day = Math.max(0, Math.min(1, (LOW_DAY.none - noonAltDeg) / (LOW_DAY.none - LOW_DAY.full)));
  if (day <= 0 || altDeg <= 0) return 0;
  // how close to the day's highest sun we are: near noon -> full, near the horizon -> keep warmth
  const r = altDeg / Math.max(0.5, noonAltDeg);
  const x = Math.max(0, Math.min(1, (r - 0.35) / 0.55));
  return day * x * x * (3 - 2 * x);
}

export function lightingFor(altDeg: number, azDeg: number, noonAltDeg = 90): Lighting {
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

  let sunColor = c((k) => k.sunColor);
  let sunIntensity = n((k) => k.sunIntensity);
  let hemiSky = c((k) => k.hemiSky);
  let hemiIntensity = n((k) => k.hemiIntensity);
  let zenith = c((k) => k.zenith);
  let fog = c((k) => k.fog);
  let hemiGround = c((k) => k.hemiGround);
  let saturation = n((k) => k.saturation);
  const w = lowSunWeight(altDeg, noonAltDeg);
  if (w > 0) {
    const L = (hex: string) => hexToLinear(hex);
    sunColor = mix(sunColor, L(LOW_DAY.sun), 0.75 * w);
    sunIntensity *= 1 - 0.12 * w;
    horizon = mix(horizon, L(LOW_DAY.horizon), 0.75 * w);
    zenith = mix(zenith, L(LOW_DAY.zenith), 0.6 * w);
    fog = mix(fog, L(LOW_DAY.fog), 0.75 * w);
    hemiSky = mix(hemiSky, L(LOW_DAY.hemiSky), 0.6 * w);
    hemiIntensity *= 1 + 0.25 * w;
    hemiGround = mix(hemiGround, L(LOW_DAY.hemiGround), 0.6 * w);
    tint = mix(tint, L(LOW_DAY.tint), 0.85 * w);
    saturation *= 1 - 0.22 * w;
  }
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
    zenith,
    horizon,
    sunColor,
    sunIntensity,
    hemiSky,
    hemiGround,
    hemiIntensity,
    fog,
    fogDensity: n((k) => k.fogDensity),
    dusk: n((k) => k.dusk),
    tint,
    saturation,
    contrast: n((k) => k.contrast),
    // thin winter daylight reads a touch brighter and flatter, not dimmer and browner
    exposure: n((k) => k.exposure) + 0.12 * w,
    groundSun,
    groundShade,
    sunDisc: altDeg > -1 ? 18 + 10 * Math.min(1, Math.max(0, altDeg / 30)) : 0,
  };
}

// ---------------------------------------------------------------------------------------------
// Film look (FILM stream, additive; /app never calls it). The Phase-6 review found daytime frames
// sitting in one narrow sepia band. This pushes separation without leaving the palette: a cleaner
// warm-white horizon with a desaturated Rayleigh blue at the zenith, deeper teal-slate shade,
// brighter sunlit stone and darker sides. `k` in [0,1] blends it in (cross-grades stay smooth).
const FILM_ZENITH = hexToLinear("#5E84A8");
const FILM_HORIZON = hexToLinear("#ECEAE3");
const FILM_FOG = hexToLinear("#DAD8D0");

export function applyFilmLook(L: Lighting, altDeg: number, k: number): Lighting {
  if (k <= 0) return L;
  const day = Math.max(0, Math.min(1, (altDeg - 4) / 18)) * k;
  const shadeDeep = scale(SHADE, 0.5 + 0.3 * (1 - day));
  // paving: a little less yellow (towards its own luminance) so stone and ground separate
  const gl = 0.2126 * L.groundSun[0] + 0.7152 * L.groundSun[1] + 0.0722 * L.groundSun[2];
  const paving = mix(L.groundSun, [gl, gl, gl], 0.18 * day);
  return {
    ...L,
    zenith: mix(L.zenith, FILM_ZENITH, 0.85 * day),
    horizon: mix(L.horizon, FILM_HORIZON, 0.75 * day),
    fog: mix(L.fog, FILM_FOG, 0.75 * day),
    fogDensity: L.fogDensity * (1 - 0.15 * day),
    sunIntensity: L.sunIntensity * (1 + 0.42 * day),
    hemiIntensity: L.hemiIntensity * (1 - 0.3 * day),
    groundSun: scale(paving, 1 - 0.2 * day),
    groundShade: mix(L.groundShade, shadeDeep, 0.82 * day),
    saturation: L.saturation + 0.02 * day,
    tint: mix(L.tint, hexToLinear("#FFFCF8"), 0.75 * day),
    contrast: L.contrast + 0.08 * day,
  };
}
