"use client";
// Well-being card (Stream F): reads ONLY the route response's `wellbeing` block (Stream A,
// backend/zill/wellbeing.py). UV band (WHO), heat stress (indicative), the daylight / vitamin D
// window with its "not medical advice" line, shadow length, break prompts, overcast note.
// The weather source is labelled Live / Recorded / Representative.
import type { ReactNode } from "react";
import { colors } from "@/design/tokens";
import type { Wellbeing } from "@/lib/api";

export function weatherBadge(source: string | undefined): string {
  if (source === "live") return "Live weather";
  if (source === "cached" || source === "recorded") return "Recorded weather";
  if (source === "representative") return "Representative profile";
  return "Weather";
}

const BAND_COLOR: Record<string, string> = {
  low: colors.oasis,
  moderate: colors.brass,
  high: colors.ember,
  "very high": colors.clay,
  extreme: colors.clay,
  none: colors.oasis,
  caution: colors.brass,
  "extreme caution": colors.ember,
  danger: colors.clay,
  "extreme danger": colors.clay,
};

function Row({
  label,
  value,
  band,
  children,
}: {
  label: string;
  value: string;
  band?: string;
  children?: ReactNode;
}) {
  return (
    <div className="border-t border-[color:var(--zill-hairline)] py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="smallcaps text-[10px] text-sand/65">{label}</span>
        <span className="tabular text-[13px] text-champagne">
          {value}
          {band ? (
            <span
              className="ml-2 text-[12px]"
              style={{ color: BAND_COLOR[band] ?? colors.sand }}
            >
              {band}
            </span>
          ) : null}
        </span>
      </div>
      {children}
    </div>
  );
}

export function WellbeingCard({ w }: { w: Wellbeing }) {
  const dw = w.daylight_window;
  const prompts = w.breaks?.prompts ?? [];
  return (
    <section
      className="mt-4 border-t border-[color:var(--zill-hairline)] pt-3"
      data-testid="wellbeing-card"
      aria-label="Well-being"
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="smallcaps text-[11px] text-sand/75">Well-being</h3>
        {w.weather ? (
          <span
            className="border border-[color:var(--zill-hairline)] px-1.5 py-px text-[10px] tracking-wide text-ivory/55"
            title={w.weather.label}
          >
            {weatherBadge(w.weather.source)}
          </span>
        ) : null}
      </div>

      {dw ? (
        <div className="mt-2 flex gap-2.5 pb-2">
          <span
            aria-hidden
            className="mt-[5px] inline-block h-[7px] w-[7px] shrink-0 rounded-full"
            style={{
              background: dw.active ? colors.ember : "transparent",
              border: `1px solid ${dw.active ? colors.ember : "rgb(244 238 225 / 0.35)"}`,
            }}
          />
          <p
            className="text-[12.5px] leading-snug"
            style={{
              color: dw.active ? colors.champagne : "rgb(244 238 225 / 0.6)",
            }}
          >
            {dw.text}
          </p>
        </div>
      ) : null}

      {w.uv ? (
        <Row
          label="UV index"
          value={w.uv.index == null ? "n/a" : w.uv.index.toFixed(0)}
          band={w.uv.band !== "unknown" ? w.uv.band : undefined}
        >
          <p className="mt-1 text-[11.5px] leading-snug text-ivory/50">
            {w.uv.advice}
          </p>
        </Row>
      ) : null}

      {w.heat_stress ? (
        <Row
          label="Feels like"
          value={
            w.heat_stress.apparent_c == null
              ? "n/a"
              : `${w.heat_stress.apparent_c.toFixed(0)}°C`
          }
          band={
            w.heat_stress.band !== "unknown" ? w.heat_stress.band : undefined
          }
        >
          <p className="mt-1 text-[11.5px] leading-snug text-ivory/50">
            {w.heat_stress.advice}
            {w.heat_stress.indicative ? " (indicative)" : ""}
          </p>
        </Row>
      ) : null}

      {dw ? (
        <Row label="Sun height" value={`${dw.sun_alt_deg.toFixed(0)}°`}>
          <p className="mt-1 text-[11.5px] leading-snug text-ivory/50">
            {dw.shadow_text}
          </p>
        </Row>
      ) : null}

      {w.overcast ? (
        <p
          className="border-t border-[color:var(--zill-hairline)] py-2 text-[11.5px] leading-snug"
          style={{ color: colors.sand }}
        >
          {w.overcast.text}
        </p>
      ) : null}

      {prompts.length > 0 ? (
        <div className="border-t border-[color:var(--zill-hairline)] py-2">
          <span className="smallcaps text-[10px] text-sand/65">Breaks</span>
          <ul className="mt-1 space-y-0.5">
            {prompts.slice(0, 3).map((p) => (
              <li
                key={p.at_s}
                className="tabular text-[11.5px] leading-snug text-ivory/60"
              >
                {p.text}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="border-t border-[color:var(--zill-hairline)] pt-2 text-[10.5px] leading-snug text-ivory/40">
        {w.disclaimer ?? "Well-being guidance, not medical advice."}
        {w.weather?.label ? ` ${w.weather.label}.` : ""}
      </p>
    </section>
  );
}
