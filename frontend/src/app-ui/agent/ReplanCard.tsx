"use client";
// Replan diff card: old vs new plan from replan.diff (all numbers from the event), plus Undo.
import { colors } from "@/design/tokens";
import { useAgent } from "@/state/useAgent";

type Side = { depart?: string; arrive?: string; rhl?: number; duration_s?: number; sun_exposure_s?: number };

export function hhmm(iso: string | undefined): string {
  const m = /T(\d{2}:\d{2})/.exec(iso ?? "");
  return m ? m[1]! : "--:--";
}

const KIND_LABEL: Record<string, string> = {
  delay: "Delay",
  closure: "Closure",
  heat_alert: "Heat alert",
};

export function ReplanCard() {
  const rp = useAgent((s) => s.replan);
  const mode = useAgent((s) => s.session?.mode);
  const busy = useAgent((s) => s.busy);
  const undo = useAgent((s) => s.undo);
  if (!rp) return null;
  const d = rp.diff;
  const oldP = (d.old ?? {}) as Side;
  const newP = (d.new ?? {}) as Side;
  const delta = typeof d.delta_rhl_pct === "number" ? d.delta_rhl_pct : null;
  const delay = typeof d.delay_s === "number" ? d.delay_s : null;
  const canUndo = !rp.undone && (mode === "replay" || !!rp.undoToken) && (rp.auto || mode === "replay");
  const row = (label: string, a: string, b: string) => (
    <div className="grid grid-cols-[72px_1fr_16px_1fr] items-baseline py-0.5 text-[13px]">
      <span className="text-ivory/45">{label}</span>
      <span className="tabular text-ivory/60">{a}</span>
      <span className="text-ivory/30">&rarr;</span>
      <span className="tabular text-champagne">{b}</span>
    </div>
  );
  return (
    <div
      className="my-2 border px-3 py-3"
      style={{ borderColor: `${colors.ember}88` }}
      data-testid="agent-replan"
    >
      <p className="smallcaps text-[10px]" style={{ color: colors.ember }}>
        Simulated event &middot; {KIND_LABEL[rp.kind] ?? rp.kind}
      </p>
      <p className="smallcaps mt-0.5 text-[10px] text-ivory/45">
        {rp.undone ? "Reverted" : rp.auto ? "Applied automatically" : "Proposed"}
      </p>
      <p className="mt-1.5 text-[13px] leading-snug text-ivory/80">{rp.reason}</p>
      <div className="mt-2 border-t border-[color:var(--zill-hairline)] pt-2">
        {row("Depart", hhmm(oldP.depart), hhmm(newP.depart))}
        {row("Arrive", hhmm(oldP.arrive), hhmm(newP.arrive))}
        {typeof oldP.rhl === "number" && typeof newP.rhl === "number"
          ? row("Heat load", oldP.rhl.toFixed(0), newP.rhl.toFixed(0))
          : null}
      </div>
      <p className="tabular mt-1.5 text-[12px] text-ivory/50">
        {delay !== null ? `Delay ${(delay / 60).toFixed(0)} min` : ""}
        {delay !== null && delta !== null ? " · " : ""}
        {delta !== null ? `Heat load ${delta > 0 ? "+" : delta < 0 ? "−" : "±"}${Math.abs(delta).toFixed(1)}%` : ""}
      </p>
      {canUndo ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void undo()}
          className="mt-2.5 border border-[color:var(--zill-hairline)] px-4 py-1.5 text-[13px] text-ivory/80 transition-colors hover:border-ember/60 hover:text-champagne disabled:opacity-40"
          data-testid="agent-undo"
        >
          Undo
        </button>
      ) : null}
    </div>
  );
}
