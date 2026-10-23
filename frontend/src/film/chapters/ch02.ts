// Ch.2 "The problem." (50 s) — street level near the hero origin at the hero departure time on the
// hero date (hero.json; the PRD's 13:30 was written before the scenario search ran), hard light and
// a very subtle heat shimmer. A traveller walks the FASTEST hero route (slate); the ember counter
// is the route's computed sun exposure so far and ends exactly on fastest.stats.sun_exposure_s.
import { colors } from "@/design/tokens";
import type { RigState } from "@/three/rigs";
import { ramp, rampIO, win } from "../ease";
import { chaseCam, departMinutes, frameGeo, hudFor, lerpRig, routePoint, travel } from "../helpers";
import type { ChapterFn, RouteGeo } from "../types";

/** point on the route, extrapolated backwards along the first heading for d < 0 */
function behind(geo: RouteGeo, d: number) {
  if (d >= 0) return routePoint(geo, d);
  const p = routePoint(geo, 0);
  const h = routePoint(geo, 6).heading;
  return { x: p.x + Math.sin(h) * d, z: p.z - Math.cos(h) * d, heading: h };
}

export const CH2_DUR = 50;
/** Shot A runs in real time (a person walking), shot B time-lapses the rest of the route. */
const A0 = 2.5;
const A1 = 22;
const B1 = 44;

export const ch02: ChapterFn = (t, data) => {
  const s = t * CH2_DUR;
  const geo = data.heroGeo.fastest;
  const route = geo.route;
  const dur = route.stats.duration_s;
  // traveller clock: real time in shot A, then an eased time-lapse to arrival
  const fA = (A1 - A0) / dur;
  const f =
    s < A1 ? Math.max(0, (s - A0) / dur) : fA + (1 - fA) * rampIO(s, A1 + 0.6, B1);
  const tr = travel(geo, f);
  const dep = departMinutes(data.hero.depart);

  let camera: RigState;
  if (s < A1 + 0.6) {
    // Shot A: a leading Steadicam shot at the walker's pace — eye level, the lens turned back
    // towards the Burj when the route starts near it (so the street, the sun-hit paving and the
    // landmark read), otherwise straight down the route.
    const cam = behind(geo, tr.d + 3);
    const ahead = routePoint(geo, tr.d + 40);
    const toBurj = Math.hypot(cam.x, cam.z) < 900;
    const tx = toBurj ? 0 : cam.x + (ahead.x - cam.x) * 2.2;
    const tz = toBurj ? 0 : cam.z + (ahead.z - cam.z) * 2.2;
    camera = {
      // just above the canopy line so trees frame, rather than fill, the shot
      position: [cam.x, toBurj ? 9 : 1.7, cam.z],
      target: [tx, toBurj ? 95 + 30 * ramp(s, 0, A1) : 4, tz],
      fov: toBurj ? 44 : 40,
      roll: 0,
    };
  } else {
    // Shot B: low chase aerial that rises with the time-lapse, then pulls back to the whole route
    const up = 45 + 45 * rampIO(s, A1, B1);
    const c = chaseCam(geo, tr.d, 110, up, 33, 0.45);
    const start = chaseCam(geo, tr.d, 50, 22, 34, 0.45);
    const chase = lerpRig(start, c, rampIO(s, A1 + 0.6, A1 + 6));
    camera = lerpRig(chase, frameGeo(geo, 205, 1.05, 0.85, 32), rampIO(s, B1 - 3, CH2_DUR));
  }

  const hud = hudFor(data, geo, f, dep, false);
  return {
    camera,
    sun: { dateKey: data.hero.date_id, minutes: dep + tr.elapsedS / 60 },
    look: 1,
    shimmer: s < A1 + 0.6 ? 1 : 0,
    routes: {
      result: "hero",
      view: "presentation",
      selected: "fastest",
      reveal: { fastest: 1, coolest: 0 },
      opacity: 1,
    },
    // the marker only once we leave the walker's eyes
    travellers: s < A1 + 0.6 ? [] : [{ key: "fastest", scenario: data.hero.id, at: tr.at, color: colors.slate }],
    routeWidth: 1 + 0.9 * rampIO(s, A1, CH2_DUR),
    overlays: [
      { kind: "title", text: "The problem.", opacity: win(s, 0.8, 5.2, 1, 1), size: "card" },
      {
        kind: "hud",
        opacity: win(s, A0 + 1, CH2_DUR + 1, 1.2, 0.01),
        hud: { ...hud, cls: undefined, color: colors.ember },
        position: "center",
        label: "fastest",
      },
      { kind: "caption", text: "Maps optimise for time.", opacity: win(s, 9, 20, 1.2, 1.2) },
      { kind: "caption", text: "Nobody optimises for shade.", opacity: win(s, 29, 48.5, 1.2, 1.5) },
    ],
  };
};
