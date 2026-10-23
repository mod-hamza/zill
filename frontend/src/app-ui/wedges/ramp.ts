// Exposure ramp as CSS colours (brand tokens).
import { exposureRamp } from "@/design/tokens";

function hex(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Exposure 0 (shade) .. 1 (sun) -> CSS colour along the brand ramp. */
export function rampCss(v: number): string {
  const x = Math.max(0, Math.min(1, v));
  const stops = exposureRamp;
  for (let i = 1; i < stops.length; i++) {
    const a = stops[i - 1]!;
    const b = stops[i]!;
    if (x <= b.at) {
      const t = (x - a.at) / (b.at - a.at || 1);
      const ca = hex(a.color);
      const cb = hex(b.color);
      return `rgb(${ca.map((c, k) => Math.round(c + (cb[k]! - c) * t)).join(",")})`;
    }
  }
  return stops[stops.length - 1]!.color;
}

