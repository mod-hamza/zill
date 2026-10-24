"use client";
// Day / shift timeline for a /api/plan response: per-leg shade strips, cool-down breaks,
// totals and (crew) policy conflicts. Every number is read from the response.
import { colors } from "@/design/tokens";
import type { PlanResponse } from "@/lib/agentApi";
import type { Segment } from "@/lib/api";
import { fmtKm } from "@/lib/format";
import { hhmmOf, num, ShadeStrip, Stat, StripLegend, txt } from "./common";

const min = (s: number) => (s / 60).toFixed(0);

type Item = Record<string, unknown>;

function legSegments(plan: PlanResponse, legIndex: number): Segment[] {
  const leg = plan.legs[legIndex] as { route?: { segments?: Segment[] } } | undefined;
  return leg?.route?.segments ?? [];
}

export function PolicyBlock({ policy }: { policy: Record<string, unknown> | null }) {
  if (!policy) return null;
  const violations = Array.isArray(policy.violations) ? (policy.violations as Item[]) : [];
  const ok = policy.ok === true;
  return (
    <div className="mt-4 border border-[color:var(--zill-hairline)] px-3 py-3" data-testid="policy-block">
      <div className="flex items-baseline justify-between gap-2">
        <p className="smallcaps text-[10px] text-sand/70">{txt(policy.label, "Policy pack")}</p>
        <p className="smallcaps text-[10px]" style={{ color: ok ? colors.oasis : colors.clay }}>
          {ok ? "No conflicts" : `${violations.length} conflict${violations.length === 1 ? "" : "s"}`}
        </p>
      </div>
      {policy.verified !== true ? (
        <p className="mt-1 text-[11px] leading-snug text-ivory/45">
          Based on the MoHRE 2025 midday break announcement. Not legal advice.
        </p>
      ) : null}
      {violations.map((v, i) => (
        <p key={i} className="mt-2 text-[12.5px] leading-snug text-ivory/80">
          <span className="smallcaps mr-2 text-[10px]" style={{ color: colors.clay }}>
            {txt(v.rule).replace(/_/g, " ")}
          </span>
          {txt(v.item)}
          {typeof v.overlap_min === "number" ? `, ${v.overlap_min.toFixed(0)} min inside the window` : ""}
          {typeof v.run_min === "number" ? `, ${v.run_min.toFixed(0)} min continuous sun` : ""}
        </p>
      ))}
      {typeof policy.next_compliant === "string" ? (
        <p className="tabular mt-2 text-[12px] text-ivory/55">Next compliant time {hhmmOf(policy.next_compliant)}</p>
      ) : null}
    </div>
  );
}

export function PlanResult({ plan, breakKinds }: { plan: PlanResponse; breakKinds?: Record<string, string> }) {
  const t = plan.totals;
  let legIdx = 0;
  return (
    <div className="mt-4" data-testid="plan-result">
      <div className="grid grid-cols-3 gap-4 border-y border-[color:var(--zill-hairline)] py-3">
        <Stat label="Duration" value={min(num(t.duration_s))} unit="min" />
        <Stat label="In sun" value={min(num(t.sun_exposure_s))} unit="min" tone={colors.ember} />
        <Stat label="Cool-downs" value={String(num(t.breaks))} />
      </div>
      <p className="tabular mt-2 text-[12px] text-ivory/50">
        {hhmmOf(t.start)} to {hhmmOf(t.end)} &middot; {fmtKm(num(t.walk_distance_m))} travelled
        {num(t.late_stops) > 0 ? ` · ${num(t.late_stops)} late stop${num(t.late_stops) === 1 ? "" : "s"}` : ""}
      </p>

      <ol className="mt-4 list-none p-0">
        {plan.items.map((it, i) => {
          const kind = txt(it.kind);
          const isLeg = kind === "leg";
          const segs = isLeg ? legSegments(plan, legIdx++) : [];
          const tone =
            kind === "break" ? colors.oasis : kind === "work" ? colors.ember : isLeg ? colors.bronze : colors.slate;
          return (
            <li
              key={i}
              className="grid grid-cols-[44px_8px_1fr] items-start gap-x-3 pb-3"
              data-testid={`plan-item-${kind}`}
            >
              <span className="tabular pt-[3px] text-right text-[11px] text-ivory/45">{hhmmOf(it.start)}</span>
              <span className="mt-[7px] inline-block h-[6px] w-[6px] rounded-full" style={{ background: tone }} />
              <div className="min-w-0">
                <p className="text-[13.5px] leading-snug text-ivory/90">
                  {kind === "break" ? (
                    <>
                      {txt(it.label)}
                      {breakKinds?.[txt(it.poi)] ? (
                        <span className="smallcaps ml-2 text-[10px] text-oasis">{breakKinds[txt(it.poi)]}</span>
                      ) : null}
                    </>
                  ) : (
                    txt(it.label)
                  )}
                </p>
                <p className="tabular mt-0.5 text-[12px] text-ivory/50">
                  {hhmmOf(it.start)}&ndash;{hhmmOf(it.end)}
                  {isLeg
                    ? ` · ${fmtKm(num(it.distance_m))} · ${min(num(it.sun_exposure_s))} min sun · ${Math.round(num(it.shaded_pct))}% shade`
                    : kind === "work" || kind === "dwell"
                      ? typeof it.site_sun === "number"
                        ? ` · ${Math.round(it.site_sun * 100)}% site sun`
                        : ""
                      : ""}
                </p>
                {isLeg && segs.length ? (
                  <div className="mt-1.5">
                    <ShadeStrip segments={segs} />
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
      <StripLegend />
      {plan.notes.map((n, i) => (
        <p key={i} className="mt-2 text-[12px] italic text-ivory/50">
          {n}
        </p>
      ))}
      <PolicyBlock policy={plan.policy} />
    </div>
  );
}
