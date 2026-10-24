"use client";
// Panels for the Zill & Shams chapters ("Two directions", "Winter in Oslo", "Who pays" pricing,
// "Does it work?" accuracy, "Safe and cheap to run"). Pure views: every number is read from
// FilmData — hero.json / hero_oslo.json `sun` scenarios, /api/route at load, and facts.json
// (extracted verbatim from docs/COSTS.md, SECURITY.md, ACCURACY.md). Missing values render the
// nothing (the row is dropped); nothing is authored or rounded beyond display formatting.
import { colors } from "@/design/tokens";
import type { Route, Wellbeing } from "@/lib/api";
import { SHADE_ROUTE } from "../chapters/directions";
import { longDate } from "../chapters/oslo";
import type { CaseRouteStats, FilmData, LoadRow, OverlayItem } from "../types";

const n0 = (v: number) => Math.round(v).toLocaleString("en-GB");
const min1 = (s: number) => (s / 60).toFixed(1);
const reveal = (p: number, i: number, n = 5) => Math.min(1, Math.max(0, p * n - i));

/** text if present, else nothing (never a placeholder on screen) */
function ToFill({ text }: { text?: string | null }) {
  return text ? <>{text}</> : null;
}

/** the number if present, else nothing */
function N({ v, f = n0 }: { v: number | null | undefined; f?: (x: number) => string }) {
  return v === null || v === undefined ? null : <>{f(v)}</>;
}
const has = (...v: (number | string | null | undefined)[]) => v.every((x) => x !== null && x !== undefined);

function RouteRow({ label, color, r, i, p, note }: { label: string; color: string; r: Route; i: number; p: number; note?: string }) {
  return (
    <div className="film-dir-row" style={{ opacity: reveal(p, i, 4) }}>
      <i style={{ background: color }} />
      <span className="smallcaps" style={{ color }}>
        {label}
      </span>
      <span className="font-display tabular film-dir-v">
        {min1(r.stats.sun_exposure_s)}
        <small> min in sun</small>
      </span>
      <span className="tabular film-dir-sub">
        {min1(r.stats.duration_s)} min walk · {n0(r.stats.distance_m)} m{note ? ` · ${note}` : ""}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
function Directions({ o, data }: { o: Extract<OverlayItem, { kind: "directions" }>; data: FilmData }) {
  const d = data.directions;
  if (!d) return null;
  const sc = d.scenario;
  const sun = sc.sunniest;
  if (!sun) return null;
  const date = longDate(data.meta.dates[sc.date_id] ?? sc.date_id);
  const head = (
    <>
      <p className="font-display film-vignette-h">
        {sc.origin.name} &rarr; {sc.dest.name}
      </p>
      <span className="smallcaps film-panel-sub">
        {date} · {sc.depart} · walking
      </span>
    </>
  );
  if (o.phase === "shade" && d.shade)
    return (
      <div className="film-panel film-dir" style={{ opacity: o.opacity }}>
        <span className="smallcaps film-panel-k">Shade mode · least direct sun</span>
        {head}
        <RouteRow label="Fastest" color={colors.slate} r={sc.fastest} i={0} p={o.progress} />
        <RouteRow label="Shadiest" color={SHADE_ROUTE} r={d.shade} i={1} p={o.progress} />
      </div>
    );
  if (o.phase === "sun") {
    const st = sun.stats;
    return (
      <div className="film-panel film-dir" style={{ opacity: o.opacity }}>
        <span className="smallcaps film-panel-k">Sun mode · most direct sun, for well-being</span>
        {head}
        <RouteRow label="Fastest" color={colors.slate} r={sc.fastest} i={0} p={o.progress} />
        <RouteRow label="Sunniest" color={colors.ember} r={sun} i={1} p={o.progress} />
        {st.sun_gained_s !== undefined ? (
          <p className="tabular film-dir-gain" style={{ opacity: reveal(o.progress, 2, 4) }}>
            +{min1(st.sun_gained_s)} min of direct sun for +{min1(st.added_time_s)} min of walking
          </p>
        ) : null}
      </div>
    );
  }
  if (o.phase === "both" && d.shade)
    return (
      <div className="film-panel film-dir" style={{ opacity: o.opacity }}>
        <span className="smallcaps film-panel-k">One engine · two directions · minutes in direct sun</span>
        {head}
        <div className="film-dir-cols" style={{ opacity: reveal(o.progress, 0, 3) }}>
          {[
            { k: "Shade mode", r: d.shade, c: SHADE_ROUTE },
            { k: "Fastest", r: sc.fastest, c: colors.slate },
            { k: "Sun mode", r: sun, c: colors.ember },
          ].map((x) => (
            <div key={x.k}>
              <span className="font-display tabular" style={{ color: x.c }}>
                {min1(x.r.stats.sun_exposure_s)}
              </span>
              <span className="smallcaps">{x.k}</span>
            </div>
          ))}
        </div>
        <span className="film-panel-sub" style={{ opacity: reveal(o.progress, 1, 3) }}>
          The person chooses the direction. Model estimate, not a measurement.
        </span>
      </div>
    );
  return null;
}

// ---------------------------------------------------------------------------------------------
function WellbeingCard({ o, data }: { o: Extract<OverlayItem, { kind: "wellbeing" }>; data: FilmData }) {
  const w: Wellbeing | null | undefined =
    o.which === "oslo" ? data.oslo?.scenario.wellbeing : data.directions?.scenario.wellbeing;
  if (!w) return null;
  const dw = w.daylight_window;
  return (
    <div className="film-panel film-wb" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">Well-being</span>
      {w.uv ? (
        <div className="film-wb-row">
          <span className="smallcaps">UV index</span>
          <span className="tabular">
            {w.uv.index === null ? "—" : w.uv.index.toFixed(1)} <em>{w.uv.band}</em>
          </span>
        </div>
      ) : null}
      {w.heat_stress ? (
        <div className="film-wb-row">
          <span className="smallcaps">Feels like</span>
          <span className="tabular">
            {w.heat_stress.apparent_c === null ? "—" : `${w.heat_stress.apparent_c.toFixed(0)}°C`} <em>heat stress: {w.heat_stress.band}</em>
          </span>
        </div>
      ) : null}
      {dw ? (
        <div className="film-wb-row">
          <span className="smallcaps">Sun height</span>
          <span className="tabular">
            {dw.sun_alt_deg.toFixed(1)}° <em>{dw.shadow_text}</em>
          </span>
        </div>
      ) : null}
      {dw ? (
        <p className="film-wb-window">
          <i style={{ background: dw.active ? colors.ember : "transparent", borderColor: dw.active ? colors.ember : "rgb(244 238 225 / 0.4)" }} />
          {dw.active ? "Daylight / vitamin D window open" : "No daylight / vitamin D window at this time"}
        </p>
      ) : null}
      <span className="film-tag">{w.disclaimer ?? "Well-being guidance, not medical advice."}</span>
      {w.weather?.source ? (
        <span className="film-wb-src">
          Weather: {w.weather.source === "live" ? "Live" : "Recorded"} · UV: WHO bands
        </span>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
function Oslo({ o, data }: { o: Extract<OverlayItem, { kind: "oslo" }>; data: FilmData }) {
  const os = data.oslo;
  const sun = os?.scenario.sunniest;
  if (!os || !sun) return null;
  const sc = os.scenario;
  const st = sun.stats;
  const c = os.meta.counts;
  return (
    <div className="film-panel film-dir" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">{os.meta.name} · sun mode · the second city</span>
      <p className="font-display film-vignette-h">
        {sc.origin.name} &rarr; {sc.dest.name}
      </p>
      <span className="smallcaps film-panel-sub">
        {longDate(os.meta.dates[sc.date_id] ?? sc.date_id)} · {sc.depart} · walking
      </span>
      <RouteRow label="Fastest" color={colors.slate} r={sc.fastest} i={0} p={o.progress} />
      <RouteRow label="Sunniest" color={colors.ember} r={sun} i={1} p={o.progress} />
      {st.sun_gained_s !== undefined ? (
        <p className="tabular film-dir-gain" style={{ opacity: reveal(o.progress, 2, 4) }}>
          +{min1(st.sun_gained_s)} min of direct sun for +{min1(st.added_time_s)} min of walking
        </p>
      ) : null}
      <span className="film-panel-sub" style={{ opacity: reveal(o.progress, 3, 4) }}>
        Same open-data pipeline: {n0(c.buildings ?? 0)} buildings · {n0(c.edges_walk ?? 0)} walkable edges ·{" "}
        {n0(c.trees ?? 0)} trees
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
function Privacy({ o, data }: { o: Extract<OverlayItem, { kind: "privacy" }>; data: FilmData }) {
  const sec = data.facts?.security;
  const a = [
    "No accounts. No ads. No trackers.",
    "Your location computes one route, then it is gone: never stored, never logged.",
    "The AI key stays on the server.",
  ];
  const b = [
    "Rate limits per IP, tightest on the AI agent",
    "Security headers: CSP, HSTS, no framing",
    sec?.body_cap_kb ? `Request size capped at ${sec.body_cap_kb} KB, input lengths capped` : "Request size and input lengths capped",
    "API locked to our own domain (CORS)",
  ];
  return (
    <div className="film-panel film-safe" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">Privacy by design</span>
      <ul className="film-safe-big">
        {a.map((x, i) => (
          <li key={x} className="font-display" style={{ opacity: reveal(o.progress, i, 6) }}>
            {x}
          </li>
        ))}
      </ul>
      <span className="smallcaps film-panel-k" style={{ marginTop: 6 }}>
        Hardening on the live site
      </span>
      <ul className="film-safe-list">
        {b.map((x, i) => (
          <li key={x} style={{ opacity: reveal(o.progress, i + 2, 6) }}>
            {x}
          </li>
        ))}
        {has(sec?.tests) ? (
          <li style={{ opacity: reveal(o.progress, 5, 6) }}>
            <N v={sec?.tests} /> security tests in the suite
          </li>
        ) : null}
      </ul>
      <span className="film-tag">UAE PDPL / GDPR alignment: an aim, not a certification</span>
    </div>
  );
}

function bestLocal(rows: LoadRow[]): LoadRow | null {
  return rows.reduce<LoadRow | null>((b, r) => (r.rps !== null && (b === null || (b.rps ?? 0) < r.rps) ? r : b), null);
}
function topLive(rows: LoadRow[]): LoadRow | null {
  return rows.reduce<LoadRow | null>((b, r) => (r.users !== null && (b === null || (b.users ?? 0) < r.users) ? r : b), null);
}

function Costs({ o, data }: { o: Extract<OverlayItem, { kind: "costs" }>; data: FilmData }) {
  const c = data.facts?.costs;
  const loc = bestLocal(c?.local_load ?? []);
  const live = topLive(c?.live_load ?? []);
  const llm = (m: string) => c?.llm.find((x) => x.model === m)?.go_conversations_month ?? null;
  const all: [string, React.ReactNode, boolean][] = [
    ["Server (VPS) per month", <ToFill key="vps" text={c?.vps_price} />, !!c?.vps_price],
    [
      "One API worker (local machine)",
      <>
        <N v={loc?.rps} f={(x) => x.toFixed(1)} /> requests/s at <N v={loc?.users} /> concurrent users · p95 <N v={loc?.p95_ms} /> ms ·{" "}
        <N v={loc?.errors} /> errors
      </>,
      has(loc?.rps, loc?.users, loc?.p95_ms, loc?.errors),
    ],
    [
      "Live server, gentle test",
      <>
        <N v={live?.users} /> concurrent users · p95 <N v={live?.p95_ms} /> ms · <N v={live?.errors} /> errors
      </>,
      has(live?.users, live?.p95_ms, live?.errors),
    ],
    [
      "AI agent (OpenCode Go)",
      <>
        $<N v={c?.go_usd_month} />/month ≈ <N v={llm("glm-5.3-flash")} /> conversations (glm-5.3-flash), <N v={llm("kimi-k3")} /> on
        kimi-k3
      </>,
      has(c?.go_usd_month, llm("glm-5.3-flash"), llm("kimi-k3")),
    ],
    [
      "A new city",
      <>
        open data, free · shade bake <N v={c?.shade_bake_s} f={(x) => x.toFixed(1)} /> s for {c?.shade_bake_dates} dates
      </>,
      has(c?.shade_bake_s, c?.shade_bake_dates),
    ],
  ];
  const rows = all.filter((r) => r[2]).map(([k, v]) => [k, v] as [string, React.ReactNode]);
  return (
    <div className="film-panel film-costs" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">What it costs to run · how many users</span>
      <table>
        <tbody>
          {rows.map(([k, v], i) => (
            <tr key={k} style={{ opacity: reveal(o.progress, i, 6) }}>
              <th className="smallcaps">{k}</th>
              <td className="tabular">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <span className="film-panel-sub" style={{ opacity: reveal(o.progress, 5, 6) }}>
        Measured 2026-10-23 ({c?.source ?? "docs/COSTS.md"}). First limit: the single API worker, not money.
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
function Accuracy({ o, data }: { o: Extract<OverlayItem, { kind: "accuracy" }>; data: FilmData }) {
  const a = data.facts?.accuracy;
  const keep = (rows: [string, React.ReactNode, boolean][]) => rows.filter((r) => r[2]).map(([k, v]) => [k, v] as [string, React.ReactNode]);
  const up = keep([
    ["Shadows", <>every <N v={a?.shadow_step_min} /> min · <N v={a?.grid_m} /> m grid</>, has(a?.shadow_step_min, a?.grid_m)],
    ["Weather", "hourly (Open-Meteo)", !!a?.weather_hourly],
    ["Departure times", <>every <N v={a?.departure_step_min} /> min</>, has(a?.departure_step_min)],
    ["Maps", a?.weekly_rebake === "planned" ? "re-baked from OpenStreetMap on demand · weekly job planned" : "re-baked from OpenStreetMap on demand", true],
  ]);
  const acc = keep([
    ["Sun position", <>within <N v={a?.sun_within_deg} f={(x) => String(x)} />° of the reference model</>, has(a?.sun_within_deg)],
    ["Building heights", <><N v={a?.heights_fallback_pct} />% of Dubai footprints use typical heights by type</>, has(a?.heights_fallback_pct)],
    ["Field validation", "pending: no accuracy percentage claimed", a?.field_validation === "pending"],
  ]);
  const table = (rows: [string, React.ReactNode][], off: number) => (
    <table className="tabular">
      <tbody>
        {rows.map(([k, v], i) => (
          <tr key={k} style={{ opacity: reveal(o.progress, i + off, 8) }}>
            <th>{k}</th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <div className="film-panel film-field film-acc" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">How often it updates</span>
      {table(up, 0)}
      <span className="smallcaps film-panel-k" style={{ marginTop: 12 }}>
        How accurate
      </span>
      {table(acc, 4)}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
function Pricing({ o }: { o: Extract<OverlayItem, { kind: "pricing" }> }) {
  const items = [
    "Free app",
    "Optional premium: saved routes, day plans",
    "B2B subscriptions are the main revenue",
    "No ads: your location is never sold",
  ];
  return (
    <div className="film-pricing" style={{ opacity: o.opacity }}>
      <span className="smallcaps">Freemium</span>
      {items.map((x) => (
        <span key={x} className="font-display">
          {x}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Short cut "Case studies": every number is case_studies.json's (verbatim, one decimal as stored).
// The who/what lines are presentation copy; company names are example target customers only.
const CASE_COPY: Record<string, { k: string; h: string; note?: string }> = {
  hotel_guest: { k: "Hotels → their guests", h: "A shaded walk from the hotel, instead of a cab." },
  delivery_rider: {
    k: "Responsible employers → their riders",
    h: "Less direct sun on every delivery trip.",
    note: "Example target customers: delivery fleets such as Talabat or Noon. Not partners or clients.",
  },
  run_dubai_dawn: { k: "Running clubs · Dubai summer", h: "A dawn run that stays in the shade." },
  winter_daylight: { k: "Winter cities → residents", h: "More daylight on a December walk." },
  run_oslo_lunch: { k: "Running clubs · Oslo winter", h: "A sunny lunchtime run." },
};
const MODE_WORD: Record<string, string> = { walk: "walking", cycle: "cycling", scooter: "scooter", run: "running" };
const pace = (m?: number) => (m ? `${Math.floor(m)}:${String(Math.round((m % 1) * 60)).padStart(2, "0")} min/km` : null);

function CaseRow({ label, color, st, i, p }: { label: string; color: string; st: CaseRouteStats; i: number; p: number }) {
  if (st.direct_sun_min === undefined) return null;
  return (
    <div className="film-dir-row" style={{ opacity: reveal(p, i, 5) }}>
      <i style={{ background: color }} />
      <span className="smallcaps" style={{ color }}>
        {label}
      </span>
      <span className="font-display tabular film-dir-v">
        {st.direct_sun_min.toFixed(1)}
        <small> min in direct sun</small>
      </span>
      {st.duration_min !== undefined && st.distance_m !== undefined ? (
        <span className="tabular film-dir-sub">
          {st.duration_min.toFixed(1)} min · {(st.distance_m / 1000).toFixed(1)} km
        </span>
      ) : null}
    </div>
  );
}

function CaseStudyPanel({ o, data }: { o: Extract<OverlayItem, { kind: "casestudy" }>; data: FilmData }) {
  const cs = data.cases[o.index];
  if (!cs) return null;
  const c = cs.c;
  const copy = CASE_COPY[c.id] ?? { k: c.label ?? c.persona ?? "Case study", h: c.label ?? "" };
  const sun = c.preference === "sun";
  const d = c.delta ?? {};
  // ONE headline: shade mode -> % less direct sun; sun mode -> minutes of direct sun gained
  const head = sun
    ? d.sun_gained_min !== undefined
      ? { v: `+${d.sun_gained_min.toFixed(1)}`, u: "min of direct sun" }
      : null
    : d.sun_saved_pct !== undefined
      ? { v: `${Math.round(d.sun_saved_pct)}%`, u: "less direct sun" }
      : null;
  const perTrip = c.persona === "rider" ? " per trip" : "";
  const color = sun ? colors.ember : colors.brass;
  const loop = !!c.turnaround;
  const date = c.date ? longDate(c.date) : (data.cityDates[c.city]?.[c.date_id] ? longDate(data.cityDates[c.city]![c.date_id]!) : null);
  const meta = [date, c.depart, MODE_WORD[c.mode] ?? c.mode].filter(Boolean).join(" · ");
  const city = c.city === "oslo" ? "Oslo" : "Dubai";
  const uv = c.wellbeing?.uv_index;
  const ps = c.per_shift;
  return (
    <div className="film-panel film-dir film-case" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">
        {copy.k} · {city}
      </span>
      <p className="font-display film-vignette-h">{copy.h}</p>
      <span className="smallcaps film-panel-sub">
        {c.origin.name} &rarr; {loop ? `${c.turnaround} → back` : c.dest.name}
      </span>
      <span className="smallcaps film-panel-sub">{meta}</span>
      {head ? (
        <p className="font-display tabular film-vignette-num film-case-num" style={{ color, opacity: reveal(o.progress, 0, 5) }}>
          {head.v} <small>{head.u}{perTrip}</small>
        </p>
      ) : null}
      {c.fastest ? <CaseRow label="Fastest" color={colors.slate} st={c.fastest} i={1} p={o.progress} /> : null}
      {c.best ? <CaseRow label={sun ? "Sunniest" : "Shadiest"} color={color} st={c.best} i={2} p={o.progress} /> : null}
      {d.added_time_min !== undefined ? (
        <p className="tabular film-dir-gain" style={{ opacity: reveal(o.progress, 3, 5) }}>
          for {d.added_time_min.toFixed(1)} min more {c.mode === "run" ? "running" : c.mode === "cycle" ? "riding" : "walking"}
          {loop ? " over the whole loop" : ""}
        </p>
      ) : null}
      <div className="film-case-notes" style={{ opacity: reveal(o.progress, 4, 5) }}>
        {copy.note ? <span className="film-panel-sub">{copy.note}</span> : null}
        {ps?.is_assumption && ps.trips !== undefined && ps.sun_saved_min !== undefined ? (
          <span className="film-panel-sub">
            Assumption, not measured: {ps.trips} such trips a shift ≈ {ps.sun_saved_min.toFixed(1)} min less direct sun.
          </span>
        ) : null}
        {sun && uv !== undefined && uv !== null ? (
          <span className="film-panel-sub">Daylight and mood, not vitamin D: UV {uv.toFixed(1)}.</span>
        ) : null}
        {c.mode === "run" && pace(c.pace?.min_per_km) ? (
          <span className="film-panel-sub">Assumed pace {pace(c.pace?.min_per_km)} · outbound leg drawn</span>
        ) : null}
        <span className="film-tag">Engine estimate, not a measurement</span>
      </div>
    </div>
  );
}

export function PivotPanels({ o, data }: { o: OverlayItem; data: FilmData }) {
  switch (o.kind) {
    case "directions":
      return <Directions o={o} data={data} />;
    case "wellbeing":
      return <WellbeingCard o={o} data={data} />;
    case "oslo":
      return <Oslo o={o} data={data} />;
    case "privacy":
      return <Privacy o={o} data={data} />;
    case "costs":
      return <Costs o={o} data={data} />;
    case "accuracy":
      return <Accuracy o={o} data={data} />;
    case "pricing":
      return <Pricing o={o} />;
    case "casestudy":
      return <CaseStudyPanel o={o} data={data} />;
    default:
      return null;
  }
}
