"use client";
// Ordered stop list with gazetteer search (/api/gazetteer), drag-to-reorder (plus up/down buttons
// for keyboard use) and per-stop dwell minutes. Shared by the planner and the crew view.
import { useEffect, useRef, useState } from "react";
import { planApi, type GazHit } from "@/lib/agentApi";
import { useCity } from "@/state/city";

export type EditorStop = { uid: number; poi: string; name: string; dwell_min: number };

let uid = 1;
export const newStop = (poi: string, name: string, dwell_min = 0): EditorStop => ({
  uid: uid++,
  poi,
  name,
  dwell_min,
});

export function StopEditor({
  stops,
  onChange,
  dwellLabel = "min",
  max = 8,
}: {
  stops: EditorStop[];
  onChange: (s: EditorStop[]) => void;
  dwellLabel?: string;
  max?: number;
}) {
  const city = useCity((s) => s.cityId);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<GazHit[]>([]);
  const [drag, setDrag] = useState<number | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) {
      setHits([]);
      return;
    }
    const mine = ++seq.current;
    const id = window.setTimeout(() => {
      planApi
        .gazetteer(city, t)
        .then((r) => {
          if (mine === seq.current) setHits(r.results);
        })
        .catch(() => {
          if (mine === seq.current) setHits([]);
        });
    }, 180);
    return () => window.clearTimeout(id);
  }, [q, city]);

  const move = (from: number, to: number) => {
    if (to < 0 || to >= stops.length || from === to) return;
    const next = stops.slice();
    const [it] = next.splice(from, 1);
    next.splice(to, 0, it!);
    onChange(next);
  };

  return (
    <div>
      <ol className="m-0 list-none p-0" data-testid="stop-list">
        {stops.map((s, i) => (
          <li
            key={s.uid}
            draggable
            onDragStart={() => setDrag(i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (drag !== null) move(drag, i);
              setDrag(null);
            }}
            onDragEnd={() => setDrag(null)}
            className={`grid grid-cols-[18px_1fr_auto_auto] items-center gap-2 border-b border-[color:var(--zill-hairline)] py-2 ${
              drag === i ? "opacity-40" : ""
            }`}
            data-testid="stop-row"
          >
            <span className="tabular text-[11px] text-brass">{i === 0 ? "A" : i}</span>
            <span className="truncate text-[14px] text-ivory/90">{s.name}</span>
            <label className="flex items-center gap-1 text-[11px] text-ivory/45">
              <input
                type="number"
                min={0}
                max={480}
                value={s.dwell_min}
                aria-label={`Minutes at ${s.name}`}
                onChange={(e) =>
                  onChange(stops.map((x) => (x.uid === s.uid ? { ...x, dwell_min: Math.max(0, Number(e.target.value) || 0) } : x)))
                }
                className="tabular w-11 border-b border-[color:var(--zill-hairline)] bg-transparent text-right text-[13px] text-champagne outline-none focus:border-sand/50"
              />
              {dwellLabel}
            </label>
            <span className="flex">
              <button type="button" aria-label={`Move ${s.name} up`} onClick={() => move(i, i - 1)} className="px-1 text-[12px] text-ivory/40 hover:text-ivory">
                &uarr;
              </button>
              <button type="button" aria-label={`Move ${s.name} down`} onClick={() => move(i, i + 1)} className="px-1 text-[12px] text-ivory/40 hover:text-ivory">
                &darr;
              </button>
              <button
                type="button"
                aria-label={`Remove ${s.name}`}
                onClick={() => onChange(stops.filter((x) => x.uid !== s.uid))}
                className="px-1 text-[12px] text-ivory/40 hover:text-clay"
              >
                &times;
              </button>
            </span>
          </li>
        ))}
      </ol>
      {stops.length < max ? (
        <div className="relative mt-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={stops.length === 0 ? "Add a starting point" : "Add a stop"}
            aria-label="Search places to add"
            spellCheck={false}
            className="zill-command w-full border-0 border-b border-[color:var(--zill-hairline)] bg-transparent pb-1.5 font-display text-[16px] font-light text-champagne outline-none placeholder:text-champagne/40 focus:border-sand/40"
            data-testid="stop-search"
          />
          {hits.length > 0 ? (
            <ul className="absolute left-0 right-0 top-full z-10 mt-1 border border-[color:var(--zill-hairline)] bg-umber">
              {hits.map((h) => (
                <li key={h.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange([...stops, newStop(h.id, h.name, stops.length === 0 ? 0 : 15)]);
                      setQ("");
                      setHits([]);
                    }}
                    className="flex w-full items-baseline justify-between px-3 py-1.5 text-left text-[13px] text-ivory/85 hover:bg-stone"
                  >
                    <span className="truncate">{h.name}</span>
                    <span className="smallcaps ml-2 text-[10px] text-sand/50">{h.kind ?? ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
