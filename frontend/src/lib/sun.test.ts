import { describe, expect, it } from "vitest";
import golden from "../../../data/curated/sun_golden.json";
import geoGolden from "../../../data/curated/geo_golden.json";
import { to_local } from "./geo";
import {
  dubaiDate,
  hhmmToMinutes,
  localIso,
  localMs,
  nowMinutes,
  sunAt,
  tzOffset,
  minutesToHHMM,
  sunPosition,
  sunTimesMinutes,
  sunVector,
} from "./sun";

type Sample = {
  ts: string;
  lat: number;
  lon: number;
  alt: number;
  alt_apparent: number;
  az: number;
};

function angDiff(a: number, b: number): number {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

describe("sun.ts vs pvlib goldens", () => {
  const samples = (golden as { samples: Sample[] }).samples;
  it("has the expected golden set", () => {
    expect(samples.length).toBeGreaterThanOrEqual(20);
  });
  for (const s of samples) {
    it(`matches ${s.ts} within 0.5 deg`, () => {
      const p = sunPosition(new Date(s.ts), s.lat, s.lon);
      expect(Math.abs(p.altDeg - s.alt_apparent)).toBeLessThan(0.5);
      expect(Math.abs(p.altDeg - s.alt)).toBeLessThan(0.5);
      expect(angDiff(p.azDeg, s.az)).toBeLessThan(0.5);
    });
  }
});

describe("sun vector convention (CONTRACTS section 2)", () => {
  it("az 90 points +x (east), az 0 points -z (north), az 180 points +z", () => {
    const e = sunVector(0, 90);
    expect(e[0]).toBeCloseTo(1, 6);
    const n = sunVector(0, 0);
    expect(n[2]).toBeCloseTo(-1, 6);
    const s = sunVector(0, 180);
    expect(s[2]).toBeCloseTo(1, 6);
    const up = sunVector(90, 37);
    expect(up[1]).toBeCloseTo(1, 6);
  });
  it("hackathon 16:00 sun is in the WSW (so shadows fall ENE)", () => {
    const p = sunPosition(dubaiDate("2026-10-24", 16 * 60), 25.1972, 55.2744);
    expect(p.azDeg).toBeGreaterThan(225);
    expect(p.azDeg).toBeLessThan(260);
    expect(p.vector[0]).toBeLessThan(0); // sun to the west
  });
  it("sunrise/sunset are plausible for Dubai", () => {
    const t = sunTimesMinutes("2026-10-24", 25.1972, 55.2744);
    expect(t.sunrise).toBeGreaterThan(5.5 * 60);
    expect(t.sunrise).toBeLessThan(6.6 * 60);
    expect(t.sunset).toBeGreaterThan(17.3 * 60);
    expect(t.sunset).toBeLessThan(18.2 * 60);
  });
  it("hhmm helpers round-trip", () => {
    expect(hhmmToMinutes("1330")).toBe(810);
    expect(hhmmToMinutes("07:05")).toBe(425);
    expect(minutesToHHMM(810)).toBe("1330");
    expect(minutesToHHMM(425, ":")).toBe("07:05");
  });
});

describe("geo.ts vs Python goldens", () => {
  const g = geoGolden as {
    origin: { lat: number; lon: number };
    points: { lat: number; lon: number; x: number; z: number }[];
  };
  it("agrees with backend geo.py on every golden point to < 0.01 m", () => {
    expect(g.points.length).toBeGreaterThanOrEqual(10);
    for (const p of g.points) {
      const [x, z] = to_local(p.lat, p.lon, g.origin);
      expect(Math.abs(x - p.x)).toBeLessThan(0.01);
      expect(Math.abs(z - p.z)).toBeLessThan(0.01);
    }
  });
});

describe("timezone-aware clock (Oslo, Stream F)", () => {
  it("Oslo is +01:00 in winter and +02:00 in summer", () => {
    expect(tzOffset("2026-12-21", 12 * 60, "Europe/Oslo")).toBe("+01:00");
    expect(tzOffset("2026-06-21", 12 * 60, "Europe/Oslo")).toBe("+02:00");
    expect(tzOffset("2026-10-24", 12 * 60)).toBe("+04:00");
    expect(localIso("2026-12-21", 12 * 60 + 30, "Europe/Oslo")).toBe(
      "2026-12-21T12:30:00+01:00",
    );
  });
  it("local wall time maps to the right instant across DST", () => {
    expect(localMs("2026-12-21", 12 * 60, "Europe/Oslo")).toBe(
      Date.parse("2026-12-21T11:00:00Z"),
    );
    expect(localMs("2026-06-21", 12 * 60, "Europe/Oslo")).toBe(
      Date.parse("2026-06-21T10:00:00Z"),
    );
  });
  it("midwinter noon sun in Oslo is ~6.6 deg high and in the south", () => {
    const p = sunAt("2026-12-21", 12 * 60 + 20, 59.91, 10.744, "Europe/Oslo");
    expect(p.altDeg).toBeGreaterThan(5.5);
    expect(p.altDeg).toBeLessThan(7.5);
    expect(p.azDeg).toBeGreaterThan(170);
    expect(p.azDeg).toBeLessThan(190);
  });
  it("Oslo sunrise/sunset on the winter solstice are local times", () => {
    const t = sunTimesMinutes("2026-12-21", 59.91, 10.744, "Europe/Oslo");
    expect(t.kind).toBe("day");
    expect(t.sunrise).toBeGreaterThan(9 * 60);
    expect(t.sunrise).toBeLessThan(9.6 * 60);
    expect(t.sunset).toBeGreaterThan(15 * 60);
    expect(t.sunset).toBeLessThan(15.5 * 60);
  });
  it("flags polar night instead of inventing a sunrise", () => {
    const t = sunTimesMinutes("2026-12-21", 78.22, 15.65, "Arctic/Longyearbyen");
    expect(t.kind).toBe("polar_night");
  });
  it("nowMinutes reads the wall clock in the city timezone", () => {
    const at = Date.parse("2026-12-21T11:05:00Z");
    expect(nowMinutes("Europe/Oslo", at)).toBe(12 * 60 + 5);
    expect(nowMinutes("Asia/Dubai", at)).toBe(15 * 60 + 5);
  });
});
