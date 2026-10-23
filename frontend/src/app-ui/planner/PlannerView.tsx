"use client";
// /app?view=planner — multi-stop day planner (PRD 8.5): add stops, drag to reorder, start time,
// mode -> POST /api/plan. Day timeline with per-leg shade strips and cool-down breaks.
import { useState } from "react";
import { planApi, type PlanResponse } from "@/lib/agentApi";
import type { Mode } from "@/lib/api";
import { useCity } from "@/state/city";
import { useSun } from "@/state/sun";
import { minutesToHHMM, TZ_OFFSET } from "@/lib/sun";
import { PlanResult } from "../wedges/PlanResult";
import { Banner, DrawerPanel } from "../wedges/common";
import { newStop, StopEditor, type EditorStop } from "../wedges/StopEditor";

const MODES: Mode[] = ["walk", "cycle", "scooter"];

// A sensible starting itinerary so the view is never empty; every stop is a real gazetteer id.
const EXAMPLE: [string, string, number][] = [
  ["address_downtown", "Address Downtown", 0],
  ["burj_park", "Burj Park", 20],
  ["dubai_mall", "The Dubai Mall", 60],
  ["dubai_opera", "Dubai Opera", 30],
];

export function PlannerView() {
  const city = useCity((s) => s.cityId);
  const sun = useSun();
  const [stops, setStops] = useState<EditorStop[]>(() => EXAMPLE.map(([p, n, d]) => newStop(p, n, d)));
  const [start, setStart] = useState(() => minutesToHHMM(Math.max(sun.minutes, 8 * 60), ":"));
  const [mode, setMode] = useState<Mode>("walk");
  const [reorder, setReorder] = useState(true);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (stops.length < 2) {
      setError("Add at least a start and one stop.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await planApi.plan({
        city,
        mode,
        persona: "tourist",
        stops: stops.map((s) => ({ place: { poi: s.poi }, dwell_min: s.dwell_min })),
        start_at: `${sun.dateIso}T${start}:00${TZ_OFFSET}`,
        date_key: sun.dateKey,
        reorder,
      });
      setPlan(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <DrawerPanel title="Day planner" banner={<Banner>Computed on {sun.dateIso}</Banner>}>
      <p className="mt-1 text-[12px] leading-snug text-ivory/50">
        The first stop is where you start. Drag stops to reorder, or let the planner choose the order.
      </p>
      <div className="mt-3">
        <StopEditor stops={stops} onChange={setStops} />
      </div>
      <div className="mt-4 grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2.5 text-[12px] text-ivory/60">
        <label htmlFor="planner-start">Start time</label>
        <input
          id="planner-start"
          type="time"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          className="tabular w-[112px] border-b border-[color:var(--zill-hairline)] bg-transparent text-[14px] text-champagne outline-none focus:border-sand/50"
        />
        <span>Mode</span>
        <div className="flex border border-[color:var(--zill-hairline)]" role="group" aria-label="Travel mode">
          {MODES.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
              className={`flex-1 px-2 py-1 text-[12px] capitalize ${mode === m ? "bg-stone text-champagne" : "text-ivory/55 hover:text-ivory/85"}`}
            >
              {m}
            </button>
          ))}
        </div>
        <span>Order</span>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={reorder} onChange={(e) => setReorder(e.target.checked)} />
          Let Zill choose the best order
        </label>
      </div>
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        className="mt-4 border border-brass/60 px-4 py-2.5 text-[13px] tracking-wide text-champagne transition-colors hover:bg-stone disabled:opacity-40"
        data-testid="plan-run"
      >
        {busy ? "Planning…" : "Plan my day"}
      </button>
      {error ? <p className="mt-3 text-[12px] text-clay">Planning failed: {error}</p> : null}
      {plan ? <PlanResult plan={plan} /> : null}
    </DrawerPanel>
  );
}
