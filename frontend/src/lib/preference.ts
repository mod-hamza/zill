// Shade <-> Sun wording and colours in one place (the App's cards, toggle, agent cards).
import { colors } from "@/design/tokens";
import type { Preference, RouteStats } from "./api";

export const PREFERENCES: { id: Preference; label: string; color: string; hint: string }[] = [
  {
    id: "shade",
    label: "Shade",
    color: colors.shade,
    hint: "Least direct sun",
  },
  {
    id: "sun",
    label: "Sun",
    color: colors.ember,
    hint: "Most direct sun and daylight",
  },
];

/** Label of the lambda-3 route: "Coolest" (shade mode) or "Sunniest" (sun mode). */
export function bestLabel(p: Preference | undefined): string {
  return p === "sun" ? "Sunniest" : "Coolest";
}

/** Colour of the lambda-3 route ribbon/card: brass (shade) or ember (sun). */
export function bestColor(p: Preference | undefined): string {
  return p === "sun" ? colors.ember : colors.brass;
}

/** The headline delta vs fastest, in seconds: sun saved (shade) or sun gained (sun). */
export function sunDelta(
  p: Preference | undefined,
  st: RouteStats,
): { label: "sun saved" | "sun gained"; s: number; pct: number } {
  if (p === "sun")
    return {
      label: "sun gained",
      s: st.sun_gained_s ?? -st.sun_saved_s,
      pct: st.sun_gained_pct ?? -st.sun_saved_pct,
    };
  return { label: "sun saved", s: st.sun_saved_s, pct: st.sun_saved_pct };
}
