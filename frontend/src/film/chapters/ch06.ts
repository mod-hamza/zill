// Ch.6 "The route." HERO (150 s) — command bar with the hero's real names; the recorded agent
// session streams in the activity feed (events placed proportionally to their dt_ms); both routes
// draw when compare_routes returns; FlyRig follows the COOLEST route at eye level (heights authored
// over buildings; cool interior grade on indoor / AC-link segments) with a live HUD; then a split
// view Fastest | Coolest on the same clock; final card from hero.json; "Model estimate, not a
// measurement."
import { colors } from "@/design/tokens";
import { orbitRig, type RigState } from "@/three/rigs";
import { ramp, rampIO, rampUI, typed, caretOn, win } from "../ease";
import { chaseCam, departMinutes, flyCam, frameGeo, hudFor, lerpRig, travel } from "../helpers";
import { cumOf, timeline, totalMs } from "../replay";
import type { ChapterFn, ChapterOut, FilmData } from "../types";

export const CH6_DUR = 150;
export const CH6 = {
  type0: 1.5,
  feed0: 9,
  feed1: 50,
  flyIn0: 55,
  fly0: 63,
  fly1: 115,
  split0: 118.5,
  split1: 138,
  card: 138.5,
} as const;

export function heroPrompt(data: FilmData): string {
  const r = data.replays.tourist_walk;
  const h = data.hero;
  // the recorded prompt, if it is about the hero trip; else built from hero.json names
  if (r?.prompt && r.prompt.includes(h.origin.name) && r.prompt.includes(h.dest.name)) return r.prompt;
  const verb = h.mode === "cycle" ? "I'm cycling" : h.mode === "scooter" ? "I'm on a scooter" : "I'm walking";
  return `${h.origin.name} to ${h.dest.name}, ${h.depart}, ${verb}`;
}

function aerial(data: FilmData, u: number): RigState {
  const b = data.heroGeo.coolest.bbox;
  const fb = data.heroGeo.fastest.bbox;
  const cx = (Math.min(b.x0, fb.x0) + Math.max(b.x1, fb.x1)) / 2;
  const cz = (Math.min(b.z0, fb.z0) + Math.max(b.z1, fb.z1)) / 2;
  const ext = Math.max(b.ext, fb.ext);
  return orbitRig(u, {
    target: [cx, 0, cz + ext * 0.04],
    radius: ext * 1.12,
    height: ext * 1.0,
    startDeg: 188,
    sweepDeg: 20,
    fov: 31,
    floatAmp: 0.1,
    seed: 6,
    durationS: 60,
  });
}

/** indoor/AC-link share of route time around f (smooth interior grade, no pops) */
function indoorAround(data: FilmData, f: number): number {
  const geo = data.heroGeo.coolest;
  const dur = geo.route.stats.duration_s;
  let k = 0;
  const N = 9;
  for (let i = 0; i < N; i++) {
    const ff = f + ((i - (N - 1) / 2) * 3) / dur;
    const c = travel(geo, Math.max(0, Math.min(1, ff))).cls;
    if (c === "indoor" || c === "ac_link") k += 1;
  }
  return k / N;
}

export const ch06: ChapterFn = (t, data) => {
  const s = t * CH6_DUR;
  const hero = data.hero;
  const dep = departMinutes(hero.depart);
  const cool = data.heroGeo.coolest;
  const fast = data.heroGeo.fastest;

  // feed timeline (plan phase of the recorded hero session)
  const tl = timeline(data.replays.tourist_walk, ["plan"]);
  const total = Math.max(1, totalMs(tl));
  const feedU = ramp(s, CH6.feed0, CH6.feed1);
  const cmpMs = cumOf(tl, (e) => e.type === "tool_result" && e.payload?.name === "compare_routes");
  const sCmp = cmpMs !== null ? CH6.feed0 + ((CH6.feed1 - CH6.feed0) * cmpMs) / total : 28;

  const out: ChapterOut = {
    look: 1,
    routeWidth: s < CH6.fly0 ? 1.9 : s >= CH6.split0 - 1.2 ? 1.7 : 1,
    sun: { dateKey: hero.date_id, minutes: dep },
    overlays: [],
  };
  const ov = out.overlays!;
  ov.push({ kind: "title", text: "The route.", opacity: win(s, 0.6, 4.6, 1, 1), size: "card" });

  // --- aerial + agent -------------------------------------------------------------------------
  if (s < CH6.fly0) {
    const air = aerial(data, ramp(s, 0, CH6.flyIn0));
    out.camera =
      s < CH6.flyIn0 ? air : lerpRig(aerial(data, 1), flyCam(cool, 0, 52), rampIO(s, CH6.flyIn0, CH6.fly0));
    out.routes = {
      result: "hero",
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: rampUI(s, sCmp, sCmp + 2.5), coolest: rampUI(s, sCmp + 1.8, sCmp + 5) },
      opacity: 1,
    };
    ov.push({
      kind: "command",
      text: typed(heroPrompt(data), s, CH6.type0 + 1, 18),
      caret: caretOn(s) && s < CH6.feed0,
      opacity: win(s, CH6.type0, CH6.feed1 + 2, 1, 1.5),
    });
    ov.push({
      kind: "feed",
      replayId: "tourist_walk",
      cursorMs: total * feedU,
      phases: ["plan"],
      opacity: win(s, CH6.feed0 - 0.6, CH6.flyIn0 + 1, 1, 1.5),
    });
  }

  // --- fly-through on the coolest route --------------------------------------------------------
  if (s >= CH6.fly0 && s < CH6.split0 - 1.2) {
    const f = Math.min(1, rampIO(s, CH6.fly0, CH6.fly1));
    const tr = travel(cool, f);
    const u = cool.poly.length > 0 ? tr.d / cool.poly.length : 0;
    out.camera = flyCam(cool, u, CH6.fly1 - CH6.fly0);
    out.sun = { dateKey: hero.date_id, minutes: dep + tr.elapsedS / 60 };
    out.indoor = 0.5 * indoorAround(data, f);
    out.routes = {
      result: "hero",
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: 1, coolest: 1 },
      opacity: 1,
    };
    out.travellers = [{ key: "coolest", scenario: hero.id, at: tr.at, color: colors.brass }];
    ov.push({
      kind: "hud",
      opacity: win(s, CH6.fly0 + 0.5, CH6.split0 - 1.3, 1, 0.8),
      hud: { ...hudFor(data, cool, f, dep, true), color: colors.ember },
      position: "center",
      label: "coolest",
    });
  }

  // --- split view: same clock -----------------------------------------------------------------
  if (s >= CH6.split0 - 1.2) {
    const coolDur = cool.route.stats.duration_s;
    const T = coolDur * rampIO(s, CH6.split0 + 0.8, CH6.split1);
    const fc = T / coolDur;
    const ff = Math.min(1, T / fast.route.stats.duration_s);
    const tc = travel(cool, fc);
    const tf = travel(fast, ff);
    // chase cams; once both have arrived they rise to show each whole route
    const pull = rampIO(s, CH6.split1 - 1, CH6.split1 + 7);
    const left = lerpRig(chaseCam(fast, tf.d, 120, 80, 36, 0.6), frameGeo(fast, 200, 1.0, 0.95, 36), pull);
    const right = lerpRig(chaseCam(cool, tc.d, 120, 80, 36, 0.6), frameGeo(cool, 200, 1.0, 0.95, 36), pull);
    out.camera = left;
    out.split = { amount: 1, camera: right };
    out.sun = { dateKey: hero.date_id, minutes: dep + T / 60 };
    out.routes = {
      result: "hero",
      view: "presentation",
      selected: "coolest",
      reveal: { fastest: 1, coolest: 1 },
      opacity: 1,
    };
    out.travellers = [
      { key: "fastest", scenario: hero.id, at: tf.at, color: colors.slate },
      { key: "coolest", scenario: hero.id, at: tc.at, color: colors.brass },
    ];
    const hudOp = win(s, CH6.split0, CH6.card + 0.4, 1, 1);
    ov.push({ kind: "splitline", opacity: win(s, CH6.split0, CH6_DUR + 1, 0.8, 0.01), left: "Fastest", right: "Coolest" });
    ov.push({
      kind: "hud",
      opacity: hudOp,
      hud: { ...hudFor(data, fast, ff, dep, false), clock: hudFor(data, cool, fc, dep, false).clock, color: colors.ember },
      position: "left",
      label: "fastest",
    });
    ov.push({
      kind: "hud",
      opacity: hudOp,
      hud: { ...hudFor(data, cool, fc, dep, false), color: colors.ember },
      position: "right",
      label: "coolest",
    });
    ov.push({ kind: "compare", opacity: win(s, CH6.card, CH6_DUR + 1, 1.4, 0.01) });
    ov.push({ kind: "honest", text: "Model estimate, not a measurement.", opacity: win(s, CH6.card + 2.5, CH6_DUR + 1, 1.4, 0.01) });
    // dip across the cut into the split
    out.fade = Math.max(0, 1 - Math.abs(s - (CH6.split0 - 0.4)) / 0.9);
  }
  return out;
};
