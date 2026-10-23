"use client";
// /app?view=fleet — simulated delivery fleet (PRD 16.2): N riders on the scenario corridors with
// staggered departures, each routed by POST /api/route (cycle). Aggregates are sums of the API's
// own per-route stats (coolest vs fastest); nothing is estimated client-side beyond addition.
import { useCallback, useEffect, useRef, useState } from "react";
import { colors } from "@/design/tokens";
import type { RouteResponse, Scenario } from "@/lib/api";
import { api } from "@/lib/api";
import { fmtKm } from "@/lib/format";
import { minutesToHHMM, TZ_OFFSET } from "@/lib/sun";
import { useCity } from "@/state/city";
import { useSun } from "@/state/sun";
import { Banner, DrawerPanel, ShadeStrip, Stat, StripLegend } from "./common";
import { fleetTotals } from "./fleetMath";

const N_RIDERS = 12;
const FIRST_DEPART_MIN = 12 * 60 + 30;
const STAGGER_MIN = 12;
const CONCURRENCY = 3;

type Rider = {
  id: number;
  corridor: string;
  depart: string;
  res: RouteResponse | null;
  error: string | null;
};

export function FleetView() {
  const city = useCity((s) => s.cityId);
  const dateIso = useSun((s) => s.dateIso);
  const dateKey = useSun((s) => s.dateKey);
  const [riders, setRiders] = useState<Rider[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useRef(0);

  const simulate = useCallback(async () => {
    const mine = ++run.current;
    setBusy(true);
    setError(null);
    setRiders([]);
    let corridors: Scenario[] = [];
    try {
      corridors = (await api.scenarios(city))?.scenarios ?? [];
    } catch {
      corridors = [];
    }
    if (!corridors.length) {
      setError("No scenario corridors available from the backend.");
      setBusy(false);
      return;
    }
    const plan: Rider[] = Array.from({ length: N_RIDERS }, (_, i) => {
      const c = corridors[i % corridors.length]!;
      return {
        id: i + 1,
        corridor: `${c.origin.name} to ${c.dest.name}`,
        depart: minutesToHHMM(FIRST_DEPART_MIN + i * STAGGER_MIN, ":"),
        res: null,
        error: null,
      };
    });
    setRiders(plan);
    let next = 0;
    const worker = async () => {
      while (next < plan.length && run.current === mine) {
        const i = next++;
        const c = corridors[i % corridors.length]!;
        try {
          const res = await api.route({
            city,
            mode: "cycle",
            origin: { lat: c.origin.lat, lon: c.origin.lon, node: c.origin.node },
            dest: { lat: c.dest.lat, lon: c.dest.lon, node: c.dest.node },
            depart_at: `${dateIso}T${plan[i]!.depart}:00${TZ_OFFSET}`,
            date_key: dateKey,
          });
          plan[i] = { ...plan[i]!, res };
        } catch (e) {
          plan[i] = { ...plan[i]!, error: e instanceof Error ? e.message : String(e) };
        }
        if (run.current === mine) setRiders(plan.slice());
      }
    };
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    if (run.current === mine) setBusy(false);
  }, [city, dateIso, dateKey]);

  useEffect(() => {
    void simulate();
    const token = run;
    return () => {
      token.current++;
    };
  }, [simulate]);

  const tot = fleetTotals(riders);
  const failed = riders.filter((r) => r.error).length;
  const rhlPct = tot.rhlBase > 0 ? (tot.rhlSaved / tot.rhlBase) * 100 : 0;

  return (
    <DrawerPanel title="Delivery fleet" banner={<Banner>Simulated fleet (scenario)</Banner>}>
      <p className="mt-1 text-[12px] leading-snug text-ivory/50">
        {N_RIDERS} simulated riders cycle the scenario corridors, departing every {STAGGER_MIN} minutes from{" "}
        {minutesToHHMM(FIRST_DEPART_MIN, ":")} on {dateIso}. Each compares the fastest route with the coolest.
      </p>

      <div className="mt-4 grid grid-cols-3 gap-4 border-y border-[color:var(--zill-hairline)] py-3" data-testid="fleet-totals">
        <Stat label="Sun saved" value={(tot.sunSavedS / 60).toFixed(1)} unit="min" tone={colors.oasis} />
        <Stat label="Heat load" value={`${rhlPct >= 0 ? "−" : "+"}${Math.abs(rhlPct).toFixed(0)}`} unit="%" tone={colors.oasis} />
        <Stat label="Extra distance" value={`+${(tot.extraDistanceM / 1000).toFixed(2)}`} unit="km" />
      </div>
      <p className="tabular mt-2 text-[12px] text-ivory/50">
        Summed over {tot.ok} of {N_RIDERS} riders &middot; extra time {(tot.extraTimeS / 60).toFixed(1)} min in total
        {failed ? ` · ${failed} failed` : ""}
        {busy ? " · routing…" : ""}
      </p>
      {error ? <p className="mt-3 text-[12px] text-clay">{error}</p> : null}

      <ol className="mt-4 list-none p-0" data-testid="fleet-riders">
        {riders.map((r) => {
          const f = r.res?.fastest;
          const c = r.res?.coolest;
          return (
            <li key={r.id} className="border-b border-[color:var(--zill-hairline)] py-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[13px] text-ivory/85">
                  <span className="tabular mr-2 text-[11px] text-brass">R{r.id}</span>
                  <span className="tabular text-ivory/55">{r.depart}</span>
                </span>
                {c && f ? (
                  <span className="tabular text-[12px] text-ivory/55">
                    {f.stats.sun_exposure_s - c.stats.sun_exposure_s < 3 ? (
                      <span>coolest is the fastest route</span>
                    ) : (
                      <>
                        <span style={{ color: colors.oasis }}>
                          &minus;{((f.stats.sun_exposure_s - c.stats.sun_exposure_s) / 60).toFixed(1)} min sun
                        </span>{" "}
                        &middot; +{Math.round(c.stats.distance_m - f.stats.distance_m)} m
                      </>
                    )}
                  </span>
                ) : r.error ? (
                  <span className="text-[12px] text-clay">failed</span>
                ) : (
                  <span className="text-[12px] text-ivory/35">routing&hellip;</span>
                )}
              </div>
              <p className="mt-0.5 truncate text-[11px] text-ivory/40">{r.corridor}</p>
              {f && c ? (
                <div className="mt-1.5 space-y-[3px]">
                  <ShadeStrip segments={f.segments} height={4} />
                  <ShadeStrip segments={c.segments} height={6} />
                  <p className="tabular text-[10px] text-ivory/35">
                    thin: fastest {fmtKm(f.stats.distance_m)} &middot; thick: coolest {fmtKm(c.stats.distance_m)}
                  </p>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
      {riders.length ? <StripLegend /> : null}
      <button
        type="button"
        onClick={() => void simulate()}
        disabled={busy}
        className="mt-4 border border-[color:var(--zill-hairline)] px-4 py-2 text-[12px] text-ivory/70 hover:text-champagne disabled:opacity-40"
      >
        Re-run simulation
      </button>
    </DrawerPanel>
  );
}
