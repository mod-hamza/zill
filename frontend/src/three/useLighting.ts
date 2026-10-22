// Cached time-of-day lighting derived from the sun store (recomputed only when the sun moves).
import { useSun } from "@/state/sun";
import { lightingFor, type Lighting } from "./lighting";

let lastKey = "";
let last: Lighting = lightingFor(60, 180);
/** optional override (e.g. the Film's interior "AC link" grade); null = follow the sun */
let indoorAmount = 0;

export function currentLighting(): Lighting {
  const { sun } = useSun.getState();
  const key = `${sun.altDeg.toFixed(3)}_${sun.azDeg.toFixed(3)}`;
  if (key !== lastKey) {
    last = lightingFor(sun.altDeg, sun.azDeg);
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
