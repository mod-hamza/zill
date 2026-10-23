"use client";
// /app overlay: brand, command bar, agent slot, journey panel, time bar, fly HUD, hints, limits.
import { useEffect } from "react";
import { ARABIC, NAME } from "@/brand";
import { useCity } from "@/state/city";
import { useRoute } from "@/state/route";
import { AgentPanel } from "./AgentPanel";
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
    <p className="pointer-events-none fixed bottom-[150px] left-1/2 z-20 -translate-x-1/2 text-[13px] tracking-wide text-ivory/60">
      {!a
        ? "Click the map to set a start point"
        : "Click again to set the destination"}
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
      <div className="pointer-events-auto fixed left-6 top-5 z-30">
        <div className="flex items-baseline gap-2">
          <span className="font-display text-[28px] font-light leading-none text-champagne">
            {NAME}
          </span>
          <span
            className="font-display text-[20px] leading-none text-sand/60"
            lang="ar"
          >
            {ARABIC}
          </span>
        </div>
        <p className="smallcaps mt-2 text-[10px] text-sand/55">
          {meta?.synthetic
            ? "Synthetic fixture"
            : (meta?.name ?? "Downtown Dubai")}
        </p>
      </div>
      <CommandBar />
      <AgentPanel />
      <ViewHost />
      <JourneyPanel />
      <Hint />
      <FlyHud />
      <TimeBar />
    </div>
  );
}
