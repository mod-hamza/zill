// PRD 12.3 palette. Mirrored as CSS variables (--zill-*) in globals.css.
export const colors = {
  ink: "#0E0C0A",
  umber: "#1A1511",
  stone: "#2A231C",
  sand: "#D8C7A3",
  champagne: "#E9DCBC",
  ivory: "#F4EEE1",
  bronze: "#A06A3B",
  brass: "#C8A15A",
  ember: "#D07A35",
  clay: "#9C4F3B",
  shade: "#22333A",
  oasis: "#5E8C7B",
  slate: "#7C8A94",
} as const;

export type ColorToken = keyof typeof colors;

// Exposure ramp stops: shaded -> mid -> sun (interpolate perceptually, e.g. OKLab).
export const exposureRamp = [
  { at: 0, color: colors.shade },
  { at: 0.5, color: "#6F6A55" },
  { at: 1, color: colors.ember },
] as const;

export const easing = "cubic-bezier(0.22, 0.61, 0.36, 1)";

export const tokens = { colors, exposureRamp, easing } as const;
