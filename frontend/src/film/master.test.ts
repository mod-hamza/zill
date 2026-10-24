// Film master timeline: durations, purity/determinism, monotonic chapters, real numbers.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { CHAPTERS, CHAPTER_STARTS, TOTAL_S, chapterAt, evaluate, setCut, cutFor } from "./master";
import { pickStreet, routeGeo } from "./data";
import { travel } from "./helpers";
import { FILM_HOME_CITY, type CaseStudyJson, type FilmData, type HeroScenario, type Replay, type RouteSet } from "./types";
import { osloCaption } from "./chapters/oslo";

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
  // sun scenarios: Dubai pair (shade side stubbed with the balanced route: tests do not call the API)
  const sunSc = (hj.sun?.scenarios ?? []) as HeroScenario[];
  const d = sunSc.find((x) => x.id === "office_lunch_walk") ?? sunSc[0]!;
  const oj = read("data/scenarios/hero_oslo.json");
  const os = (oj.sun.scenarios as HeroScenario[]).find((x) => x.date_id === "winter")!;
  const set = (sc: HeroScenario, city: string, f: HeroScenario["fastest"], c: HeroScenario["fastest"], p: "shade" | "sun"): RouteSet => ({
    fastest: f, balanced: sc.balanced, coolest: c, preference: p, origin: sc.origin, dest: sc.dest, date_key: sc.date_id, city,
  });
  const routeSets: Record<string, RouteSet> = {
    dir_shade: set(d, FILM_HOME_CITY, d.fastest, d.balanced, "shade"),
    dir_sun: set(d, FILM_HOME_CITY, d.fastest, d.sunniest!, "sun"),
    dir_both: set(d, FILM_HOME_CITY, d.balanced, d.sunniest!, "sun"),
    oslo_sun: set(os, "oslo", os.fastest, os.sunniest!, "sun"),
  };
  scenarioGeo.dir_shade = geo({ ...d, coolest: d.balanced });
  scenarioGeo.dir_sun = geo({ ...d, coolest: d.sunniest! });
  scenarioGeo.dir_both = { fastest: scenarioGeo.dir_shade.coolest, coolest: scenarioGeo.dir_sun.coolest };
  scenarioGeo.oslo_sun = geo({ ...os, coolest: os.sunniest! });
  const osloMeta = read("data/cities/oslo/meta.json");
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
    directions: { scenario: d, shade: d.balanced, rule: "test" },
    oslo: { meta: osloMeta, scenario: os },
    routeSets,
    cityDates: { [FILM_HOME_CITY]: meta.dates, oslo: osloMeta.dates },
    facts: null,
    // case studies verbatim; drawn routes stubbed with the hero pair (tests do not call the API)
    cases: (read("data/scenarios/case_studies.json").cases as CaseStudyJson[])
      .sort((a, b) => Number(a.city !== FILM_HOME_CITY) - Number(b.city !== FILM_HOME_CITY))
      .map((c) => ({ c, routeKey: hero.id })),
  };
}

const data = loadData();

describe("short cut (/film)", () => {
  it("is the default, 9 chapters, 405 s; /film2 and ?cut= pick the cut", () => {
    setCut("short");
    expect(CHAPTERS.map((c) => c.id)).toEqual(["ch01", "ch03", "ch04", "directions", "cases", "agent", "who", "safety", "ask"]);
    expect(TOTAL_S).toBe(405);
    expect(cutFor("/film", "")).toBe("short");
    expect(cutFor("/film2", "")).toBe("full");
    expect(cutFor("/film", "?cut=full")).toBe("full");
    expect(cutFor("/film2", "?qa=1&cut=short")).toBe("short");
  });
  it("is pure and its chapters are monotonic", () => {
    setCut("short");
    const ts = Array.from({ length: 120 }, (_, i) => ((i * 7919) % (TOTAL_S * 10)) / 10);
    const a = ts.map((t) => JSON.stringify(evaluate(t, data)));
    const b = [...ts].reverse().map((t) => JSON.stringify(evaluate(t, data))).reverse();
    expect(a).toEqual(b);
    let last = 0;
    for (let t = 0; t <= TOTAL_S; t += 0.61) {
      const f = evaluate(t, data);
      expect(f.chapter).toBeGreaterThanOrEqual(last);
      last = f.chapter;
    }
  });
  it("case studies: every case gets a vignette, Oslo cases switch the city, no placeholder text", () => {
    setCut("short");
    const i = CHAPTERS.findIndex((c) => c.id === "cases");
    const seen = new Set<number>();
    for (let s = 5; s < CHAPTERS[i]!.dur_s; s += 0.5) {
      const f = evaluate(CHAPTER_STARTS[i]! + s, data);
      const o = f.overlays.find((x) => x.kind === "casestudy");
      if (o && o.kind === "casestudy" && o.opacity > 0.5) {
        seen.add(o.index);
        expect(f.city).toBe(data.cases[o.index]!.c.city);
      }
    }
    expect(seen.size).toBe(data.cases.length);
    for (let t = 0; t <= TOTAL_S; t += 1.3)
      expect(JSON.stringify(evaluate(t, data).overlays)).not.toMatch(/TEAM TO FILL|TO VALIDATE/i);
  });
});


describe("film master timeline (full film, /film2)", () => {
  beforeEach(() => setCut("full"));
  it("has 15 chapters summing to 790 s (13:10, about the pre-pivot 13:00)", () => {
    expect(CHAPTERS).toHaveLength(15);
    expect(TOTAL_S).toBe(790);
    expect(CHAPTER_STARTS[14]! + CHAPTERS[14]!.dur_s).toBe(790);
  });

  it("evaluate(t) is pure: same t twice -> deep-equal frames, in any order", () => {
    const ts = Array.from({ length: 160 }, (_, i) => ((i * 7919) % (TOTAL_S * 10)) / 10);
    const a = ts.map((t) => JSON.stringify(evaluate(t, data)));
    const b = [...ts].reverse().map((t) => JSON.stringify(evaluate(t, data))).reverse();
    expect(a).toEqual(b);
  });

  it("chapter index is monotonic in t and frames are finite", () => {
    let prev = -1;
    for (let t = 0; t <= TOTAL_S; t += 0.73) {
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
    for (let t = 0; t <= TOTAL_S; t += 0.5) {
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

  it("only the Oslo chapter switches the scene to Oslo, at Oslo's own date", () => {
    const io = CHAPTERS.findIndex((c) => c.id === "oslo");
    for (let t = 0; t <= TOTAL_S; t += 1.1) {
      const f = evaluate(t, data);
      expect(f.city).toBe(f.chapter === io ? "oslo" : FILM_HOME_CITY);
    }
    const mid = evaluate(CHAPTER_STARTS[io]! + 30, data);
    expect(mid.routes.result).toBe("oslo_sun");
    expect(mid.sun.dateKey).toBe(data.oslo!.scenario.date_id);
  });

  it("Oslo caption and note quote the scenario's own sun height, shadow and UV", () => {
    const w = data.oslo!.scenario.wellbeing!;
    const cap = osloCaption(data)!;
    expect(cap).toContain(`${w.daylight_window!.sun_alt_deg.toFixed(1)}°`);
    expect(cap).toContain(w.daylight_window!.shadow_text);
    const io = CHAPTERS.findIndex((c) => c.id === "oslo");
    const end = evaluate(CHAPTER_STARTS[io]! + CHAPTERS[io]!.dur_s - 1, data);
    const note = end.overlays.find((o) => o.kind === "caption" && o.opacity > 0.5);
    expect(note && note.kind === "caption" ? note.text : "").toContain(`UV ${w.uv!.index!.toFixed(1)}`);
  });

  it("Two directions shows shade, then sun, then both route sets", () => {
    const i = CHAPTERS.findIndex((c) => c.id === "directions");
    const at = (s: number) => evaluate(CHAPTER_STARTS[i]! + s * (CHAPTERS[i]!.dur_s / 50), data).routes.result;
    expect(at(10)).toBe("dir_shade");
    expect(at(25)).toBe("dir_sun");
    expect(at(45)).toBe("dir_both");
  });
});
