"use client";
// /app?view=crew — outdoor crew shift (PRD 16.3): tasks with on-site minutes plus a shift window
// -> POST /api/plan (persona crew). The UAE policy pack is data and unverified; it is labelled so.
import { useMemo, useState } from "react";
import { planApi, type PlanResponse } from "@/lib/agentApi";
import { useCity } from "@/state/city";
import { useSun } from "@/state/sun";
import { TZ_OFFSET } from "@/lib/sun";
import { hhmmOf } from "./common";
import { Banner, DrawerPanel } from "./common";
import { PlanResult } from "./PlanResult";
import { newStop, StopEditor, type EditorStop } from "./StopEditor";

const EXAMPLE: [string, string, number][] = [
  ["address_boulevard", "Address Boulevard", 0],
  ["the_waterfall", "The Waterfall", 90],
  ["address_sky_view", "Address Sky View", 60],
  ["starbucks", "Starbucks", 30],
];

export function CrewView() {
  const city = useCity((s) => s.cityId);
  const pois = useCity((s) => s.pois);
  const sun = useSun();
  const [stops, setStops] = useState<EditorStop[]>(() => EXAMPLE.map(([p, n, d]) => newStop(p, n, d)));
  const [shiftStart, setShiftStart] = useState("11:00");
  const [shiftEnd, setShiftEnd] = useState("17:00");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // cool-down venue kinds (cafe / mall / metro ...) so breaks read as AC or covered places
  const breakKinds = useMemo(() => {
    const m: Record<string, string> = {};
    for (const p of pois ?? []) m[p.id] = p.kind;
    return m;
  }, [pois]);

  const run = async () => {
    if (stops.length < 2) {
      setError("Add a depot and at least one task.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await planApi.plan({
        city,
        mode: "walk",
        persona: "crew",
        stops: stops.map((s) => ({ place: { poi: s.poi }, dwell_min: s.dwell_min })),
        start_at: `${sun.dateIso}T${shiftStart}:00${TZ_OFFSET}`,
        date_key: sun.dateKey,
        reorder: false,
        policy_pack: "UAE_OUTDOOR_WORK",
        shift_window: [`${sun.dateIso}T${shiftStart}:00${TZ_OFFSET}`, `${sun.dateIso}T${shiftEnd}:00${TZ_OFFSET}`],
      });
      setPlan(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const chosen = plan ? hhmmOf(plan.totals.start) : null;

  return (
    <DrawerPanel title="Crew shift" banner={<Banner>Simulated crew (scenario)</Banner>}>
      <p className="mt-1 text-[12px] leading-snug text-ivory/50">
        The first stop is the depot; the rest are tasks done outdoors. Zill picks the start inside the shift
        window with the fewest policy conflicts, then the lowest heat load.
      </p>
      <div className="mt-3">
        <StopEditor stops={stops} onChange={setStops} dwellLabel="min on site" />
      </div>
      <div className="mt-4 grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2.5 text-[12px] text-ivory/60">
        <span>Shift window</span>
        <span className="flex items-center gap-2">
          <input
            type="time"
            aria-label="Earliest start"
            value={shiftStart}
            onChange={(e) => setShiftStart(e.target.value)}
            className="tabular w-[112px] border-b border-[color:var(--zill-hairline)] bg-transparent text-[14px] text-champagne outline-none"
          />
          to
          <input
            type="time"
            aria-label="Latest end"
            value={shiftEnd}
            onChange={(e) => setShiftEnd(e.target.value)}
            className="tabular w-[112px] border-b border-[color:var(--zill-hairline)] bg-transparent text-[14px] text-champagne outline-none"
          />
        </span>
      </div>
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        className="mt-4 border border-brass/60 px-4 py-2.5 text-[13px] tracking-wide text-champagne transition-colors hover:bg-stone disabled:opacity-40"
        data-testid="crew-run"
      >
        {busy ? "Scheduling…" : "Schedule the shift"}
      </button>
      {error ? <p className="mt-3 text-[12px] text-clay">Scheduling failed: {error}</p> : null}
      {plan ? (
        <>
          {chosen && chosen !== shiftStart ? (
            <p className="mt-3 text-[12px] text-ivory/55">Chosen start {chosen} (window opens {shiftStart}).</p>
          ) : null}
          <PlanResult plan={plan} breakKinds={breakKinds} />
        </>
      ) : null}
    </DrawerPanel>
  );
}
