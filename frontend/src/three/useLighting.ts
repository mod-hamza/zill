// Cached time-of-day lighting derived from the sun store (recomputed only when the sun moves).
import { useSun } from "@/state/sun";
import { applyFilmLook, lightingFor, noonAltitudeDeg, type Lighting } from "./lighting";
import { sceneOverrides } from "./sceneOverrides";

let lastKey = "";
let last: Lighting = lightingFor(60, 180);
/** optional override (e.g. the Film's interior "AC link" grade); null = follow the sun */
let indoorAmount = 0;

export function currentLighting(): Lighting {
  const { sun, dateIso, origin } = useSun.getState();
  const film = sceneOverrides.filmLook;
  const key = `${sun.altDeg.toFixed(3)}_${sun.azDeg.toFixed(3)}_${film.toFixed(3)}_${dateIso}_${origin.lat.toFixed(2)}`;
  if (key !== lastKey) {
    // the day's own noon altitude drives the low-sun (high-latitude winter) grade
    const noon = noonAltitudeDeg(origin.lat, dateIso);
    last = applyFilmLook(lightingFor(sun.altDeg, sun.azDeg, noon), sun.altDeg, film);
    lastKey = key;
  }
  return last;
}

export function setIndoorAmount(v: number) {
  indoorAmount = Math.max(0, Math.min(1, v));
}
export function getIndoorAmount() {
  return indoorAmount;
}
