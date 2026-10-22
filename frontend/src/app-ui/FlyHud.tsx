"use client";
// Fly-through HUD (PRD 15): sun exposure so far, shade %, clock — all from the route's computed
// segment timings (lib/routeGeom.progressAt); nothing estimated in the UI.
import { colors } from "@/design/tokens";
import { progressAt } from "@/lib/routeGeom";
import { minutesToHHMM } from "@/lib/sun";
import { easedDistance } from "@/three/rigs";
import { FLY_ACCEL } from "@/three/AppDrivers";
import { useRoute } from "@/state/route";
import { useSun } from "@/state/sun";

export function FlyHud() {
  const flyT = useRoute((s) => s.flyT);
  const route = useRoute((s) => (s.result ? s.result[s.selected] : null));
  const minutes = useSun((s) => s.minutes);
  if (flyT === null || !route) return null;
  const p = progressAt(route, easedDistance(flyT, FLY_ACCEL));
  const indoor = p.cls === "indoor" || p.cls === "ac_link";
  const covered = p.cls === "covered";
  return (
    <div className="pointer-events-none fixed bottom-[150px] left-1/2 z-30 flex -translate-x-1/2 items-end gap-12">
      <Stat
        label="Sun exposure so far"
        value={(p.sunS / 60).toFixed(1)}
        unit="min"
        color={colors.ember}
      />
      <Stat label="Shade" value={Math.round(p.shadePct).toString()} unit="%" />
      <Stat label="Clock" value={minutesToHHMM(minutes, ":")} />
      {indoor || covered ? (
        <span
          className="smallcaps mb-2 border bg-umber/[0.92] px-2 py-1 text-[10px]"
          style={{ borderColor: colors.oasis, color: colors.oasis }}
        >
          {indoor ? "Indoor · AC link" : "Covered"}
        </span>
      ) : null}
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  color,
}: {
  label: string;
  value: string;
  unit?: string;
  color?: string;
}) {
  return (
    <div className="flex flex-col items-center">
      <span
        className="tabular font-display text-[40px] font-light leading-none"
        style={{ color: color ?? colors.champagne }}
      >
        {value}
        {unit ? (
          <span className="ml-1 font-sans text-[13px] text-ivory/60">
            {unit}
          </span>
        ) : null}
      </span>
      <span className="smallcaps mt-2 text-[10px] text-ivory/60">{label}</span>
    </div>
  );
}
