// Number formatting for the UI. Formatting only — every value comes from computed output.
export const fmtMin = (s: number) => `${(s / 60).toFixed(1)}`;
export const fmtKm = (m: number) =>
  m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
export const fmtPct = (p: number) => `${Math.round(p)}%`;
export const fmtSigned = (s: number, unit = "min") => {
  const v = s / 60;
  const sign = v > 0.05 ? "+" : v < -0.05 ? "−" : "±";
  return `${sign}${Math.abs(v).toFixed(1)} ${unit}`;
};
export function fmtDate(iso: string, tz = "Asia/Dubai"): string {
  // noon UTC on that date is the same calendar day in every timezone within +-11 h
  const d = new Date(`${iso}T12:00:00Z`);
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: tz,
  });
}
