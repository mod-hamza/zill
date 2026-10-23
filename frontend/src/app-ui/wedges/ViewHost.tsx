"use client";
// Tabs + host for the P1 views: /app?view=planner | fleet | crew. (view=analysis|presentation is
// the scene's own route-view flag and is left alone.) Opening a view closes the agent panel.
import { useCallback, useEffect, useState } from "react";
import { DEFAULT_CITY, useCity } from "@/state/city";
import { useAgent } from "@/state/useAgent";
import { PlannerView } from "../planner/PlannerView";
import { CrewView } from "./CrewView";
import { FleetView } from "./FleetView";

type ViewId = "planner" | "fleet" | "crew";
const TABS: { id: ViewId; label: string }[] = [
  { id: "planner", label: "Day plan" },
  { id: "fleet", label: "Fleet" },
  { id: "crew", label: "Crew" },
];

function readView(): ViewId | null {
  const v = new URLSearchParams(window.location.search).get("view");
  return v === "planner" || v === "fleet" || v === "crew" ? v : null;
}

export function ViewHost() {
  const [view, setView] = useState<ViewId | null>(null);
  const agentOpen = useAgent((s) => s.open);
  // the B2B views are authored around Downtown Dubai's gazetteer (depots, attractions)
  const cityId = useCity((s) => s.cityId);

  useEffect(() => {
    const v = readView();
    if (v) {
      setView(v);
      useAgent.getState().setOpen(false);
    }
  }, []);

  // opening the agent closes a view (they share the left rail)
  useEffect(() => {
    if (agentOpen) setView(null);
  }, [agentOpen]);

  const choose = useCallback((id: ViewId | null) => {
    setView(id);
    const u = new URL(window.location.href);
    if (id) u.searchParams.set("view", id);
    else if (readView()) u.searchParams.delete("view");
    window.history.replaceState(null, "", u);
    if (id) useAgent.getState().setOpen(false);
  }, []);

  if (cityId !== DEFAULT_CITY) return null;
  return (
    <>
      <nav
        className="zill-desktop-only pointer-events-auto fixed left-[112px] top-[104px] z-30 flex"
        aria-label="Views"
        data-testid="view-tabs"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            aria-pressed={view === t.id}
            onClick={() => choose(view === t.id ? null : t.id)}
            className={`smallcaps -ml-px border border-[color:var(--zill-hairline)] px-3 py-2 transition-colors ${
              view === t.id ? "bg-stone text-champagne" : "bg-umber/[0.92] text-sand/70 hover:text-champagne"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {view === "planner" ? <PlannerView /> : null}
      {view === "fleet" ? <FleetView /> : null}
      {view === "crew" ? <CrewView /> : null}
    </>
  );
}
