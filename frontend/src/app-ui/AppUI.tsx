"use client";
// /app overlay: brand, command bar, agent slot, journey panel, time bar, fly HUD, hints, limits.
import { useEffect } from "react";
import { ARABIC, NAME } from "@/brand";
import { useCity } from "@/state/city";
import { useRoute } from "@/state/route";
import { AgentPanel } from "./AgentPanel";
import { BusyNote } from "./BusyNote";
import { CitySwitch } from "./CitySwitch";
import { CommandBar } from "./CommandBar";
import { FlyHud } from "./FlyHud";
import { JourneyPanel } from "./JourneyPanel";
import { TimeBar } from "./TimeBar";
import { ViewHost } from "./wedges/ViewHost";

function Hint() {
  const a = useRoute((s) => s.a);
  const b = useRoute((s) => s.b);
  const flying = useRoute((s) => s.flyT !== null);
  if (flying || (a && b)) return null;
  return (
    <p className="zill-hint pointer-events-none fixed left-1/2 z-20 -translate-x-1/2 text-center text-[13px] tracking-wide text-ivory/60">
      {!a
        ? "Tap the map to set a start point, or type a journey above"
        : "Tap again to set the destination"}
    </p>
  );
}

export function AppUI() {
  const loaded = useCity((s) => s.loaded);
  const meta = useCity((s) => s.meta);
  const loadScenarios = useRoute((s) => s.loadScenarios);
  useEffect(() => {
    if (loaded) void loadScenarios();
  }, [loaded, loadScenarios]);

  return (
    <div className="pointer-events-none fixed inset-0 z-20">
      <div className="zill-brand pointer-events-auto fixed z-30 border border-[color:var(--zill-hairline)] bg-umber/[0.72] px-3 pb-2 pt-2.5">
        <div className="flex items-baseline gap-2">
          <span className="zill-brand-name font-display font-light leading-none text-champagne">
            {NAME}
          </span>
          <span
            className="zill-brand-ar font-display leading-none text-sand/60"
            lang="ar"
            dir="rtl"
          >
            {ARABIC}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-3">
          <p className="zill-brand-city smallcaps text-[10px] text-sand/55">
            {meta?.synthetic ? "Synthetic fixture" : (meta?.name ?? " ")}
          </p>
          <CitySwitch />
        </div>
      </div>
      <CommandBar />
      <BusyNote />
      <AgentPanel />
      <ViewHost />
      <JourneyPanel />
      <Hint />
      <FlyHud />
      <TimeBar />
    </div>
  );
}
