// Sun position for the frontend (mirrors backend/zill/sun/position.py within ~0.5 deg).
// Azimuth: degrees clockwise from north. Altitude: apparent elevation (refraction-corrected),
// matching the backend's pvlib apparent_elevation. suncalc v2 already returns degrees, north-based
// clockwise azimuth and apparent altitude (see node_modules/suncalc/index.d.ts).
// Vector toward the sun in the local frame (x east, y up, z south), CONTRACTS section 2:
//   x = sin(az) cos(alt), y = sin(alt), z = -cos(az) cos(alt)
import { getPosition, getTimes } from "suncalc";

export type SunPos = {
  altDeg: number;
  azDeg: number;
  vector: [number, number, number];
};

const DEG = Math.PI / 180;

/** Dubai has no DST; every preset date is interpreted in a fixed +04:00 offset. */
export const TZ_OFFSET = "+04:00";

/** Bennett (1982) refraction in degrees for a true altitude in degrees. */
export function refractionDeg(trueAltDeg: number): number {
  if (trueAltDeg < -1.0) return 0;
  const h = Math.max(trueAltDeg, -0.9);
  return 1.02 / Math.tan((h + 10.3 / (h + 5.11)) * DEG) / 60;
}

export function sunVector(
  altDeg: number,
  azDeg: number,
): [number, number, number] {
  const a = altDeg * DEG;
  const z = azDeg * DEG;
  return [Math.sin(z) * Math.cos(a), Math.sin(a), -Math.cos(z) * Math.cos(a)];
}

export function sunPosition(date: Date, lat: number, lon: number): SunPos {
  const p = getPosition(date, lat, lon);
  let az = p.azimuth % 360;
  if (az < 0) az += 360;
  const altDeg = p.altitude;
  return { altDeg, azDeg: az, vector: sunVector(altDeg, az) };
}

/** Build a Date for a local Dubai wall-clock time. `minutes` = minutes since local midnight. */
export function dubaiDate(isoDate: string, minutes: number): Date {
  const base = Date.parse(`${isoDate}T00:00:00${TZ_OFFSET}`);
  return new Date(base + minutes * 60_000);
}

export function sunAt(
  isoDate: string,
  minutes: number,
  lat: number,
  lon: number,
): SunPos {
  return sunPosition(dubaiDate(isoDate, minutes), lat, lon);
}

export type SunTimes = { sunrise: number; sunset: number; solarNoon: number };

/** Sunrise/sunset/solar noon as minutes since local (Dubai) midnight. */
export function sunTimesMinutes(
  isoDate: string,
  lat: number,
  lon: number,
): SunTimes {
  const noonLocal = dubaiDate(isoDate, 12 * 60);
  const t = getTimes(noonLocal, lat, lon);
  const base = Date.parse(`${isoDate}T00:00:00${TZ_OFFSET}`);
  const m = (d: Date) => (d.getTime() - base) / 60_000;
  return {
    sunrise: t.sunrise ? m(t.sunrise) : 6 * 60,
    sunset: t.sunset ? m(t.sunset) : 18 * 60,
    solarNoon: m(t.solarNoon),
  };
}

export function hhmmToMinutes(hhmm: string): number {
  const s = hhmm.replace(":", "").padStart(4, "0");
  return Number(s.slice(0, 2)) * 60 + Number(s.slice(2, 4));
}

export function minutesToHHMM(minutes: number, sep = ""): string {
  const m = Math.round(minutes);
  const h = Math.floor(m / 60) % 24;
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}${sep}${String(mm).padStart(2, "0")}`;
}
