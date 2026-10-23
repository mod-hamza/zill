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

/** Dubai has no DST: its fixed +04:00 offset. Other cities use `tzOffset(tz, ...)`. */
export const TZ_OFFSET = "+04:00";
export const DEFAULT_TZ = "Asia/Dubai";


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


const offFmt = new Map<string, Intl.DateTimeFormat>();

/** UTC offset in minutes of `tz` at the instant `utcMs` (e.g. Europe/Oslo in winter -> 60). */
export function tzOffsetMinutesAt(tz: string, utcMs: number): number {
  if (tz === DEFAULT_TZ) return 240;
  let f = offFmt.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    offFmt.set(tz, f);
  }
  const p: Record<string, number> = {};
  for (const x of f.formatToParts(new Date(utcMs)))
    if (x.type !== "literal") p[x.type] = Number(x.value);
  const asUtc = Date.UTC(p.year!, p.month! - 1, p.day!, p.hour!, p.minute!, p.second!);
  return Math.round((asUtc - Math.floor(utcMs / 1000) * 1000) / 60_000);
}

/** UTC instant (ms) of a wall-clock time in `tz`. `minutes` = minutes since local midnight. */
export function localMs(isoDate: string, minutes: number, tz = DEFAULT_TZ): number {
  const wall = Date.parse(`${isoDate}T00:00:00Z`) + minutes * 60_000;
  let off = tzOffsetMinutesAt(tz, wall);
  off = tzOffsetMinutesAt(tz, wall - off * 60_000);
  return wall - off * 60_000;
}

/** "+01:00" style offset of `tz` at that local wall-clock time (for ISO depart_at strings). */
export function tzOffset(isoDate: string, minutes: number, tz = DEFAULT_TZ): string {
  if (tz === DEFAULT_TZ) return TZ_OFFSET;
  const off = tzOffsetMinutesAt(tz, localMs(isoDate, minutes, tz));
  const a = Math.abs(off);
  return `${off < 0 ? "-" : "+"}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
}

/** ISO timestamp for a local wall-clock time in `tz`, e.g. 2026-12-21T12:00:00+01:00. */
export function localIso(isoDate: string, minutes: number, tz = DEFAULT_TZ): string {
  return `${isoDate}T${minutesToHHMM(minutes, ":")}:00${tzOffset(isoDate, minutes, tz)}`;
}

/** Build a Date for a local wall-clock time (Dubai unless `tz` is given). */
export function dubaiDate(isoDate: string, minutes: number, tz = DEFAULT_TZ): Date {
  return new Date(localMs(isoDate, minutes, tz));
}
export const localDate = dubaiDate;

/** Minutes since local midnight "now" in `tz`. */
export function nowMinutes(tz = DEFAULT_TZ, now = Date.now()): number {
  const off = tzOffsetMinutesAt(tz, now);
  const d = new Date(now + off * 60_000);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

export function sunAt(
  isoDate: string,
  minutes: number,
  lat: number,
  lon: number,
  tz = DEFAULT_TZ,
): SunPos {
  return sunPosition(dubaiDate(isoDate, minutes, tz), lat, lon);
}

export type SunTimes = {
  sunrise: number;
  sunset: number;
  solarNoon: number;
  /** "day" normal; "polar_night" sun never rises; "midnight_sun" never sets */
  kind: "day" | "polar_night" | "midnight_sun";
};

/** Sunrise/sunset/solar noon as minutes since local midnight (Dubai unless `tz` is given). */
export function sunTimesMinutes(
  isoDate: string,
  lat: number,
  lon: number,
  tz = DEFAULT_TZ,
): SunTimes {
  const noonLocal = dubaiDate(isoDate, 12 * 60, tz);
  const t = getTimes(noonLocal, lat, lon);
  const base = localMs(isoDate, 0, tz);
  const m = (d: Date) => (d.getTime() - base) / 60_000;
  const ok = (d: Date | null | undefined): d is Date =>
    !!d && Number.isFinite(d.getTime());
  const solarNoon = m(t.solarNoon);
  const rise: Date | null | undefined = t.sunrise;
  const set: Date | null | undefined = t.sunset;
  if (ok(rise) && ok(set))
    return { sunrise: m(rise), sunset: m(set), solarNoon, kind: "day" };
  const noonAlt = getPosition(t.solarNoon, lat, lon).altitude;
  return {
    sunrise: 6 * 60,
    sunset: 18 * 60,
    solarNoon,
    kind: noonAlt > 0 ? "midnight_sun" : "polar_night",
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
