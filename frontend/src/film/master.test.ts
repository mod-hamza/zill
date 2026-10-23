// Film master timeline: durations, purity/determinism, monotonic chapters, real numbers.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CHAPTERS, CHAPTER_STARTS, TOTAL_S, chapterAt, evaluate } from "./master";
import { pickStreet, routeGeo } from "./data";
import { travel } from "./helpers";
import type { FilmData, HeroScenario, Replay } from "./types";

const ROOT = join(__dirname, "..", "..", "..");
const read = (p: string) => JSON.parse(readFileSync(join(ROOT, p), "utf8"));

function loadData(): FilmData {
  const meta = read("data/cities/dubai_downtown/meta.json");
  const hj = read("data/scenarios/hero.json");
  const scenarios = hj.scenarios as HeroScenario[];
  const hero = scenarios.find((s) => s.id === "tourist_walk") ?? scenarios[0]!;
  const geo = (s: HeroScenario) => ({ fastest: routeGeo(s.fastest, null), coolest: routeGeo(s.coolest, null) });
  const scenarioGeo: FilmData["scenarioGeo"] = {};
  for (const s of scenarios) scenarioGeo[s.id] = geo(s);
  const replays: Record<string, Replay> = {};
  for (const f of readdirSync(join(ROOT, "backend", "replay")).filter((x) => x.endsWith(".json")))
    replays[f.replace(".json", "")] = read(`backend/replay/${f}`);
  const street = pickStreet(hero.coolest);
  return {
    meta,
    hero,
    scenarios,
    heroGeo: scenarioGeo[hero.id]!,
    scenarioGeo,
    labelSegs: street.labelSegs,
    streetFocus: street.focus,
    replays,
    weather: { source: "live", label: "test", apparent_c: 40 },
    tests: { backend: { passed: 1, failed: 0 }, frontend: { passed: 1, failed: 0 } },
    shadeBakeLog: [],
    acLink: hj.ac_link_story ?? null,
    acLinkArea: { x: -300, z: -400, ext: 300 },
    hotelWalks: [],
    hotelName: "Hotel",
    notes: {},
    hasFieldTest: false,
    policy: null,
    bakedCities: [{ id: "dubai_downtown", name: "Downtown Dubai", lat: 25.2, lon: 55.27 }],
    burjH: 828,
  };
}

const data = loadData();

describe("film master timeline", () => {
  it("has 12 chapters summing to 780 s (13:00)", () => {
    expect(CHAPTERS).toHaveLength(12);
    expect(TOTAL_S).toBe(780);
    expect(CHAPTER_STARTS[11]! + CHAPTERS[11]!.dur_s).toBe(780);
  });

  it("evaluate(t) is pure: same t twice -> deep-equal frames, in any order", () => {
    const ts = Array.from({ length: 160 }, (_, i) => ((i * 7919) % 7800) / 10);
    const a = ts.map((t) => JSON.stringify(evaluate(t, data)));
    const b = [...ts].reverse().map((t) => JSON.stringify(evaluate(t, data))).reverse();
    expect(a).toEqual(b);
  });

  it("chapter index is monotonic in t and frames are finite", () => {
    let prev = -1;
    for (let t = 0; t <= 780; t += 0.73) {
      const f = evaluate(t, data);
      expect(f.chapter).toBeGreaterThanOrEqual(prev);
      expect(f.chapter).toBe(chapterAt(t));
      prev = f.chapter;
      for (const v of [...f.camera.position, ...f.camera.target, f.camera.fov, f.sun.minutes])
        expect(Number.isFinite(v)).toBe(true);
    }
  });

  it("no frame shows more than 2 text overlays besides HUD/panels", () => {
    const TEXT = new Set(["title", "caption", "command", "pipeline", "honest", "closing"]);
    for (let t = 0; t <= 780; t += 0.5) {
      const n = evaluate(t, data).overlays.filter((o) => TEXT.has(o.kind) && o.opacity > 0.05).length;
      expect(n, `t=${t}`).toBeLessThanOrEqual(2);
    }
  });

  it("Ch.2 sun counter ends exactly on hero fastest sun exposure", () => {
    const geo = data.heroGeo.fastest;
    expect(travel(geo, 1).sunS).toBeCloseTo(data.hero.fastest.stats.sun_exposure_s, 6);
    const end = evaluate(CHAPTER_STARTS[1]! + CHAPTERS[1]!.dur_s - 0.01, data);
    const hud = end.overlays.find((o) => o.kind === "hud");
    expect(hud && hud.kind === "hud" ? hud.hud.sunS : -1).toBeCloseTo(data.hero.fastest.stats.sun_exposure_s, 6);
  });
});
