"use client";
// /embed/hotel?hotel=<name>[&date=summer][&time=13:30] — stand-alone, brand-neutral concierge widget
// (PRD 16.1). Nearest attractions with the coolest walk from the hotel at the chosen time. Every
// number comes from POST /api/route. "Add to my day" is a labelled mock and stores nothing.
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const CITY = "dubai_downtown";
const KINDS = new Set(["landmark", "mall", "park", "water"]);
const TIMES = ["09:00", "10:30", "12:00", "13:30", "15:00", "16:30", "18:00"];
const MAX = 5;

type Poi = { id: string; name: string; lat: number; lon: number; kind: string };
type Stats = { distance_m: number; duration_s: number; sun_exposure_s: number; shaded_pct: number };
type Row = { poi: Poi; fastest: Stats; coolest: Stats } | { poi: Poi; error: string };

const DATES: Record<string, string> = {
  winter: "2026-01-15",
  spring: "2026-04-15",
  summer: "2026-07-15",
  hackathon: "2026-10-24",
};

function distM(a: Poi, b: Poi): number {
  const dx = (a.lon - b.lon) * 111320 * Math.cos((a.lat * Math.PI) / 180);
  const dy = (a.lat - b.lat) * 110574;
  return Math.hypot(dx, dy);
}

const mins = (s: number) => (s / 60).toFixed(0);

function Widget() {
  const qs = useSearchParams();
  const hotelQ = qs.get("hotel") ?? "";
  const dateKey = qs.get("date") && DATES[qs.get("date")!] ? qs.get("date")! : "summer";
  const [time, setTime] = useState(qs.get("time") && TIMES.includes(qs.get("time")!) ? qs.get("time")! : "13:30");
  const [hotel, setHotel] = useState<Poi | null>(null);
  const [attractions, setAttractions] = useState<Poi[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // resolve the hotel and its nearest attractions once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [pr, gr] = await Promise.all([
          fetch(`/api/cities/${CITY}/files/pois.json`).then((r) => r.json() as Promise<{ pois: Poi[] }>),
          hotelQ
            ? fetch(`/api/gazetteer/${CITY}?q=${encodeURIComponent(hotelQ)}&limit=5`).then(
                (r) => r.json() as Promise<{ results: Poi[] }>,
              )
            : Promise.resolve({ results: [] as Poi[] }),
        ]);
        const all = pr.pois;
        const hit =
          gr.results.find((h) => all.find((p) => p.id === h.id)?.kind === "hotel") ??
          all.find((p) => p.kind === "hotel" && p.name.toLowerCase().includes(hotelQ.toLowerCase()));
        const h = hit ? (all.find((p) => p.id === hit.id) ?? null) : null;
        if (cancelled) return;
        if (!h) {
          setError(hotelQ ? `No hotel matching "${hotelQ}" in the gazetteer.` : "Add ?hotel=<name> to the URL.");
          return;
        }
        setHotel(h);
        setAttractions(
          all
            .filter((p) => KINDS.has(p.kind) && p.id !== h.id)
            .sort((a, b) => distM(h, a) - distM(h, b))
            .slice(0, MAX),
        );
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hotelQ]);

  // route to each attraction whenever the time changes
  useEffect(() => {
    if (!hotel || !attractions.length) return;
    let cancelled = false;
    setBusy(true);
    (async () => {
      const out = await Promise.all(
        attractions.map(async (a): Promise<Row> => {
          try {
            const r = await fetch("/api/route", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                city: CITY,
                mode: "walk",
                origin: { poi: hotel.id },
                dest: { poi: a.id },
                depart_at: `${time}`,
                date_key: dateKey,
                include_segments: false,
              }),
            });
            if (!r.ok) throw new Error(`${r.status}`);
            const j = (await r.json()) as { fastest: { stats: Stats }; coolest: { stats: Stats } };
            return { poi: a, fastest: j.fastest.stats, coolest: j.coolest.stats };
          } catch (e) {
            return { poi: a, error: e instanceof Error ? e.message : String(e) };
          }
        }),
      );
      if (!cancelled) {
        setRows(out);
        setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hotel, attractions, time, dateKey]);

  return (
    <div className="fixed inset-0 z-50 overflow-auto" style={{ background: "#F7F4EE", color: "#2A2620" }}>
      <main className="mx-auto max-w-[520px] px-5 py-6" data-testid="hotel-embed">
        <p className="text-[11px] uppercase tracking-[0.18em]" style={{ color: "#8A7F6D" }}>
          Walk cooler from
        </p>
        <h1 className="font-display mt-1 text-[26px] font-light leading-tight">{hotel?.name ?? (hotelQ || "Your hotel")}</h1>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px]" role="group" aria-label="Time of day">
          {TIMES.map((t) => (
            <button
              key={t}
              type="button"
              aria-pressed={time === t}
              onClick={() => setTime(t)}
              className="tabular border px-2.5 py-1"
              style={{
                borderColor: time === t ? "#2A2620" : "#D9D2C3",
                background: time === t ? "#2A2620" : "transparent",
                color: time === t ? "#F7F4EE" : "#4A4338",
              }}
            >
              {t}
            </button>
          ))}
        </div>
        <p className="mt-2 text-[12px]" style={{ color: "#8A7F6D" }}>
          Walking on {DATES[dateKey]}. Shade counts buildings, mapped trees and covered links only.
        </p>

        {error ? (
          <p className="mt-6 text-[14px]" style={{ color: "#9C4F3B" }}>
            {error}
          </p>
        ) : null}

        <ul className="mt-5 list-none p-0">
          {(rows.length ? rows : attractions.map((p) => ({ poi: p, pending: true }))).map((row) => {
            const r = row as Row & { pending?: boolean };
            const ok = "coolest" in r;
            const saved = ok ? (r.fastest.sun_exposure_s - r.coolest.sun_exposure_s) / 60 : 0;
            return (
              <li key={r.poi.id} className="border-t py-3.5" style={{ borderColor: "#D9D2C3" }} data-testid="hotel-attraction">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="text-[16px] font-medium">{r.poi.name}</h2>
                  {ok ? (
                    <span className="tabular text-[14px]">{mins(r.coolest.duration_s)} min</span>
                  ) : (
                    <span className="text-[12px]" style={{ color: "#8A7F6D" }}>
                      {"error" in r ? "unavailable" : "routing…"}
                    </span>
                  )}
                </div>
                {ok ? (
                  <p className="tabular mt-1 text-[13px]" style={{ color: "#4A4338" }}>
                    {Math.round(r.coolest.shaded_pct)}% shaded &middot; {mins(r.coolest.sun_exposure_s)} min in sun
                    {saved >= 0.5
                      ? ` (fastest route: ${mins(r.fastest.sun_exposure_s)} min)`
                      : " (same as the fastest route)"}
                  </p>
                ) : null}
                <button
                  type="button"
                  onClick={() => setAdded((s) => new Set(s).add(r.poi.id))}
                  disabled={added.has(r.poi.id)}
                  className="mt-2 border px-3 py-1 text-[12px]"
                  style={{ borderColor: "#B9AF9A", color: "#4A4338" }}
                >
                  {added.has(r.poi.id) ? "Added (demo only, not saved)" : "Add to my day"}
                </button>
              </li>
            );
          })}
        </ul>
        {busy ? (
          <p className="mt-2 text-[12px]" style={{ color: "#8A7F6D" }}>
            Updating walks&hellip;
          </p>
        ) : null}
        <p className="mt-6 border-t pt-3 text-[11px] leading-snug" style={{ borderColor: "#D9D2C3", color: "#8A7F6D" }}>
          &ldquo;Add to my day&rdquo; is a mock-up and saves nothing. Route data: &copy; OpenStreetMap contributors.
        </p>
      </main>
    </div>
  );
}

export default function HotelEmbedPage() {
  return (
    <Suspense fallback={null}>
      <Widget />
    </Suspense>
  );
}
