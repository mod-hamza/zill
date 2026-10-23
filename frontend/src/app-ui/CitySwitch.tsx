"use client";
// City switch (Dubai <-> Oslo, or any city GET /api/cities lists). Only "ready" cities are
// selectable; a city still baking is shown greyed with its status, never faked.
import { useEffect } from "react";
import { useCity } from "@/state/city";
import { switchCity } from "@/state/switchCity";

const SHORT: Record<string, string> = {
  dubai_downtown: "Dubai",
  oslo: "Oslo",
};

export function shortCityName(id: string, name?: string): string {
  return SHORT[id] ?? name?.replace(/^(Downtown|Central)\s+/i, "") ?? id;
}

export function CitySwitch() {
  const cities = useCity((s) => s.cities);
  const cityId = useCity((s) => s.cityId);
  const loadCities = useCity((s) => s.loadCities);
  useEffect(() => {
    void loadCities();
  }, [loadCities]);
  const list = (cities ?? []).filter((c) => c.status !== "incomplete");
  if (list.length < 2) return null;
  return (
    <div
      role="radiogroup"
      aria-label="City"
      className="flex border border-[color:var(--zill-hairline)] bg-umber/[0.85]"
      data-testid="city-switch"
    >
      {list.map((c) => {
        const on = c.id === cityId;
        const ready = c.status === "ready";
        return (
          <button
            key={c.id}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={!ready}
            onClick={() => void switchCity(c.id)}
            title={ready ? c.name : `${c.name}: ${c.status}`}
            className={`px-2.5 py-1 text-[11px] tracking-wide transition-colors ${
              on
                ? "bg-stone text-champagne"
                : "text-ivory/55 hover:text-ivory/85 disabled:opacity-35"
            }`}
          >
            {shortCityName(c.id, c.name)}
          </button>
        );
      })}
    </div>
  );
}
