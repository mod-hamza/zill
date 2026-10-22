"use client";
// Top command bar (PRD 12.6): serif placeholder, hairline underline, brass caret. Searches the
// city's gazetteer (pois.json, offline) and sets A, then B.
import { useMemo, useState } from "react";
import type { Poi } from "@/lib/api";
import { useCity } from "@/state/city";
import { useRoute } from "@/state/route";

function score(p: Poi, q: string): number {
  const n = p.name.toLowerCase();
  const s = q.toLowerCase().trim();
  if (!s) return 0;
  if (n.startsWith(s)) return 3;
  if (n.split(/[\s/,-]+/).some((w) => w.startsWith(s))) return 2;
  return n.includes(s) ? 1 : 0;
}

export function CommandBar() {
  const pois = useCity((s) => s.pois);
  const graph = useCity((s) => s.graph);
  const a = useRoute((s) => s.a);
  const b = useRoute((s) => s.b);
  const [q, setQ] = useState("");
  const [focus, setFocus] = useState(false);

  const hits = useMemo(() => {
    if (!pois || !q.trim()) return [];
    return pois
      .map((p) => ({ p, s: score(p, q) }))
      .filter((x) => x.s > 0)
      .sort((x, y) => y.s - x.s || x.p.name.localeCompare(y.p.name))
      .slice(0, 6)
      .map((x) => x.p);
  }, [pois, q]);

  const pick = (p: Poi) => {
    const node = p.node ?? (graph ? graph.nearest(p.x, p.z) : -1);
    useRoute
      .getState()
      .clickPoint({
        node,
        x: p.x,
        z: p.z,
        lat: p.lat,
        lon: p.lon,
        name: p.name,
      });
    setQ("");
  };

  const placeholder = !a
    ? "Where are you starting?"
    : !b
      ? "And where to?"
      : "Search Downtown Dubai";

  return (
    <div className="pointer-events-auto fixed left-1/2 top-6 z-40 w-[min(560px,calc(100vw-48px))] -translate-x-1/2">
      <div className="relative">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => window.setTimeout(() => setFocus(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && hits[0]) pick(hits[0]);
            if (e.key === "Escape") setQ("");
          }}
          placeholder={placeholder}
          aria-label="Search a place"
          spellCheck={false}
          className="zill-command w-full border-0 border-b border-[color:var(--zill-hairline)] bg-transparent pb-2 pt-1 text-center font-display text-[22px] font-light text-champagne outline-none placeholder:text-champagne/45 focus:border-sand/40"
        />
        {focus && hits.length > 0 ? (
          <ul className="absolute left-0 right-0 top-full mt-2 border border-[color:var(--zill-hairline)] bg-umber/[0.92]">
            {hits.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pick(p)}
                  className="flex w-full items-baseline justify-between px-4 py-2 text-left text-[14px] text-ivory/85 hover:bg-stone"
                >
                  <span>{p.name}</span>
                  <span className="smallcaps text-[10px] text-sand/50">
                    {p.kind}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
