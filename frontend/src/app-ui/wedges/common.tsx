"use client";
// Shared bits for the planner / fleet / crew views: panel chrome, exposure strip, stats, helpers.
import type { ReactNode } from "react";
import { colors } from "@/design/tokens";
import type { Segment } from "@/lib/api";
import { rampCss } from "./ramp";

export function hhmmOf(iso: unknown): string {
  const m = /T(\d{2}:\d{2})/.exec(typeof iso === "string" ? iso : "");
  return m ? m[1]! : "--:--";
}

export const num = (v: unknown, d = 0): number => (typeof v === "number" && Number.isFinite(v) ? v : d);
export const txt = (v: unknown, d = ""): string => (typeof v === "string" ? v : d);

/** Per-leg shade strip: one cell per segment, width proportional to its travel time, colour by
 *  sun fraction; covered / indoor / AC-linked segments are drawn in oasis. */
export function ShadeStrip({ segments, height = 8 }: { segments: Segment[]; height?: number }) {
  const total = segments.reduce((a, s) => a + Math.max(0, s.t_s), 0);
  if (!segments.length || total <= 0) return null;
  return (
    <div
      className="flex w-full overflow-hidden"
      style={{ height, background: colors.stone }}
      role="img"
      aria-label="Exposure along this leg: shade to sun"
      data-testid="shade-strip"
    >
      {segments.map((s, i) => (
        <span
          key={i}
          style={{
            width: `${(Math.max(0, s.t_s) / total) * 100}%`,
            background: s.cls && s.cls !== "open" ? colors.oasis : rampCss(s.sun),
          }}
        />
      ))}
    </div>
  );
}

export function StripLegend() {
  return (
    <p className="mt-1 flex items-center gap-2 text-[10px] text-ivory/40">
      <span className="inline-block h-[6px] w-10" style={{ background: `linear-gradient(90deg, ${rampCss(0)}, ${rampCss(0.5)}, ${rampCss(1)})` }} />
      shade to sun
      <span className="ml-2 inline-block h-[6px] w-3" style={{ background: colors.oasis }} />
      covered or indoor
    </p>
  );
}

export function Stat({ label, value, unit, tone }: { label: string; value: string; unit?: string; tone?: string }) {
  return (
    <div>
      <p className="smallcaps text-[10px] text-sand/60">{label}</p>
      <p className="tabular font-display text-[26px] font-light leading-none" style={{ color: tone ?? colors.champagne }}>
        {value}
        {unit ? <span className="ml-1 font-sans text-[12px] text-ivory/50">{unit}</span> : null}
      </p>
    </div>
  );
}

export function Banner({ children, tone = colors.brass }: { children: ReactNode; tone?: string }) {
  return (
    <p
      className="smallcaps inline-block border px-2 py-[3px] text-[10px] leading-none"
      style={{ borderColor: `${tone}66`, color: tone }}
    >
      {children}
    </p>
  );
}

export function DrawerPanel({ title, banner, children }: { title: string; banner?: ReactNode; children: ReactNode }) {
  return (
    <aside
      style={{ colorScheme: "dark" }}
      className="pointer-events-auto fixed left-6 top-[152px] z-30 flex max-h-[calc(100vh-320px)] min-h-[320px] w-[420px] flex-col overflow-y-auto border border-[color:var(--zill-hairline)] bg-umber/[0.94] px-5 pb-5 pt-4"
      data-testid="view-panel"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-[20px] font-light text-champagne">{title}</h2>
        {banner}
      </div>
      {children}
    </aside>
  );
}
