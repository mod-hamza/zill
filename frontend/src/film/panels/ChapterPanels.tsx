"use client";
// Panels for chapters 8–12. Every number comes from FilmData (hero.json scenarios, recorded agent
// sessions, meta.json, test_results.json, /api/route for the concierge walks); text that is a PRD
// business hypothesis is labelled as such; market sizes are [TEAM TO FILL] placeholders.
import { colors } from "@/design/tokens";
import { fmtSigned } from "@/lib/format";
import { hhmmToMinutes } from "@/lib/sun";
import { personaScenarios } from "../chapters/ch08";
import { closingLine, TEAM } from "../chapters/ch12";
import { payloadOf, timeline } from "../replay";
import type { FilmData, FrameState, OverlayItem } from "../types";

const n0 = (v: number) => Math.round(v).toLocaleString("en-GB");
const min1 = (s: number) => (s / 60).toFixed(1);
const hm = (iso?: string) => (iso ? iso.slice(11, 16) : "—");

function ToFill({ what }: { what?: string }) {
  return (
    <span className="film-tofill" title={what}>
      [TEAM TO FILL — cite source]
    </span>
  );
}

const PERSONA_LABEL: Record<string, string> = {
  tourist: "Tourist · walking",
  rider: "Delivery rider · cycling",
  crew: "Outdoor crew · walking",
};

function Personas({ o, data }: { o: Extract<OverlayItem, { kind: "personas" }>; data: FilmData }) {
  const ps = personaScenarios(data);
  return (
    <div className="film-panel film-personas" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">Same engine · different goals</span>
      {ps.map((sc, i) => {
        const on = i === o.active;
        const st = sc.coolest.stats;
        const r = data.replays[sc.id];
        return (
          <div key={sc.id} className={`film-persona ${on ? "is-on" : ""}`}>
            <span className="smallcaps">{PERSONA_LABEL[sc.persona] ?? sc.persona}</span>
            {on ? (
              <>
                <p className="font-display">&ldquo;{r?.prompt ?? `${sc.origin.name} to ${sc.dest.name}, ${sc.depart}`}&rdquo;</p>
                <p className="tabular film-persona-num">
                  coolest route: sun {fmtSigned(-st.sun_saved_s)} &middot; time {fmtSigned(st.added_time_s)} &middot; RHL −
                  {st.rhl_saved_pct.toFixed(0)}%
                </p>
              </>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

type Diff = { old?: Record<string, number | string>; new?: Record<string, number | string> };

function Replan({ o, data }: { o: Extract<OverlayItem, { kind: "replan" }>; data: FilmData }) {
  const tl = timeline(data.replays.replan_demo, ["monitor"]);
  const rp = payloadOf<{ reason?: string; kind?: string; diff?: Diff }>(tl, "replan");
  const commit = tl.find((x) => x.event.type === "plan_committed")?.event.payload as { auto?: boolean } | undefined;
  const ticks = tl.filter((x) => x.event.type === "monitor_tick").map((x) => x.event.payload as { note?: string; status?: string });
  const note = ticks.find((x) => x.status === "replanned")?.note;
  const planTl = timeline(data.replays.replan_demo, ["plan"]);
  const ver = payloadOf<{ checked?: number; passed?: number }>(planTl, "verifier");
  const start = data.replays.replan_demo?.events[0]?.event.payload as { autonomy_level?: number } | undefined;
  const od = rp?.diff?.old;
  const nd = rp?.diff?.new;
  const delay =
    od?.depart && nd?.depart ? hhmmToMinutes(hm(String(nd.depart))) - hhmmToMinutes(hm(String(od.depart))) : null;
  const row = (k: string, label: string, f: (v: number | string) => string) => (
    <tr key={k}>
      <th className="smallcaps">{label}</th>
      <td className="tabular">{od?.[k] !== undefined ? f(od[k]!) : "—"}</td>
      <td className="tabular" style={{ color: colors.champagne }}>
        {nd?.[k] !== undefined ? f(nd[k]!) : "—"}
      </td>
    </tr>
  );
  if (!rp) return null;
  const p = o.progress;
  return (
    <div className="film-panel film-replan" style={{ opacity: o.opacity }}>
      <span className="film-badge" style={{ borderColor: `${colors.ember}88`, color: colors.ember }}>
        Simulated event{delay !== null ? ` · departure delayed ${delay} min` : ""}
      </span>
      <table style={{ opacity: p > 0.15 ? 1 : 0 }}>
        <thead>
          <tr>
            <th />
            <th className="smallcaps">Plan</th>
            <th className="smallcaps">Replanned</th>
          </tr>
        </thead>
        <tbody>
          {row("depart", "Leave", (v) => hm(String(v)))}
          {row("arrive", "Arrive", (v) => hm(String(v)))}
          {row("sun_exposure_s", "In sun", (v) => `${min1(Number(v))} min`)}
          {row("rhl", "Heat load", (v) => n0(Number(v)))}
        </tbody>
      </table>
      <p className="font-display film-replan-decision" style={{ opacity: p > 0.5 ? 1 : 0 }}>
        {commit?.auto ? `Within your L${start?.autonomy_level ?? "?"} limit → auto-applied` : "Waiting for approval"}
        {note ? <span>{note}</span> : null}
      </p>
      <div className="film-replan-foot" style={{ opacity: p > 0.7 ? 1 : 0 }}>
        <span className="film-approve">Undo</span>
        {ver ? (
          <span className="film-badge" style={{ borderColor: `${colors.oasis}88`, color: colors.oasis }}>
            Verifier {ver.passed}/{ver.checked} claims supported
          </span>
        ) : null}
      </div>
    </div>
  );
}

function Architecture({ o, data }: { o: Extract<OverlayItem, { kind: "architecture" }>; data: FilmData }) {
  const tools = new Set<string>();
  for (const r of Object.values(data.replays))
    for (const e of r.events)
      if (e.event.type === "tool_call") {
        const n = (e.event.payload as { name?: string }).name;
        if (n) tools.add(n);
      }
  const roles = ["Planner", "Verifier", "Monitor", "Narrator"];
  return (
    <div className="film-arch" style={{ opacity: o.opacity }}>
      <div className="film-arch-roles">
        {roles.map((r, i) => (
          <span key={r} className="font-display" style={{ opacity: Math.min(1, Math.max(0.15, o.progress * 5 - i)) }}>
            {r}
          </span>
        ))}
      </div>
      <p className="film-arch-tools tabular">
        {[...tools].map((t) => t.replace(/_/g, " ")).join("  ·  ")}
      </p>
    </div>
  );
}

function Vignette({ o, data }: { o: Extract<OverlayItem, { kind: "vignette" }>; data: FilmData }) {
  if (o.which === "hotel") {
    const date = data.meta.dates[data.hero.date_id] ?? "";
    return (
      <div className="film-panel film-vignette" style={{ opacity: o.opacity }}>
        <span className="smallcaps film-panel-k">Hotels &amp; tourism boards · concierge widget</span>
        <p className="font-display film-vignette-h">{data.hotelName ?? <ToFill what="hotel" />}</p>
        <span className="smallcaps film-panel-sub">
          Shade-safe walks from the lobby · {date} {data.hero.depart} · computed by the engine
        </span>
        {data.hotelWalks.length ? (
          <ol className="film-walks">
            {data.hotelWalks.map((w, i) => (
              <li key={w.dest} style={{ opacity: Math.min(1, Math.max(0, o.progress * 4 - i)) }}>
                <span className="font-display">{w.dest}</span>
                <span className="tabular">
                  {min1(w.route.stats.duration_s)} min · {Math.round(w.route.stats.shaded_pct)}% shade ·{" "}
                  {min1(w.route.stats.sun_exposure_s)} min sun
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="film-panel-sub">Walks unavailable (backend /api/route not reachable).</p>
        )}
      </div>
    );
  }
  if (o.which === "fleet") {
    const sc = data.scenarios.find((s) => s.id === "rider_cycle");
    if (!sc) return null;
    const st = sc.coolest.stats;
    return (
      <div className="film-panel film-vignette" style={{ opacity: o.opacity }}>
        <span className="smallcaps film-panel-k">Delivery fleets · rider dashboard</span>
        <p className="font-display film-vignette-h">
          {sc.origin.name} &rarr; {sc.dest.name}
        </p>
        <p className="font-display tabular film-vignette-num" style={{ color: colors.champagne }}>
          {fmtSigned(-st.sun_saved_s)} <small>in sun per trip</small>
        </p>
        <span className="tabular film-panel-sub">
          time {fmtSigned(st.added_time_s)} · heat load −{st.rhl_saved_pct.toFixed(0)}% · cycling · {sc.depart}
        </span>
        <span className="film-panel-sub">
          Per shift: trips per shift <ToFill what="trips per rider shift" />
        </span>
      </div>
    );
  }
  // crew
  const sc = data.scenarios.find((s) => s.id === "crew_shuttle");
  const w = data.policy?.midday_window;
  const commit = timeline(data.replays.crew_shuttle, ["approve"]).find((x) => x.event.type === "plan_committed")
    ?.event.payload as { summary?: { depart?: string; arrive?: string } } | undefined;
  const t0 = 12 * 60;
  const t1 = 16 * 60;
  const X = (m: number) => ((m - t0) / (t1 - t0)) * 100;
  const req = sc ? hhmmToMinutes(sc.depart) : null;
  const ok = commit?.summary?.depart ? hhmmToMinutes(hm(commit.summary.depart)) : null;
  return (
    <div className="film-panel film-vignette" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">Outdoor crews · shift planner</span>
      <p className="font-display film-vignette-h">
        {sc ? `${sc.origin.name} → ${sc.dest.name}` : <ToFill />}
      </p>
      <div className="film-timeline">
        {w ? (
          <div className="film-timeline-band" style={{ left: `${X(hhmmToMinutes(w.start))}%`, width: `${X(hhmmToMinutes(w.end)) - X(hhmmToMinutes(w.start))}%` }}>
            <span className="smallcaps">Midday break {w.start}–{w.end}</span>
          </div>
        ) : null}
        {req !== null ? (
          <i className="film-timeline-mark is-req" style={{ left: `${X(req)}%`, opacity: o.progress > 0.2 ? 1 : 0 }}>
            <span className="tabular">{sc?.depart} requested</span>
          </i>
        ) : null}
        {ok !== null ? (
          <i className="film-timeline-mark is-ok" style={{ left: `${X(ok)}%`, opacity: o.progress > 0.6 ? 1 : 0 }}>
            <span className="tabular">{hm(commit?.summary?.depart)} compliant</span>
          </i>
        ) : null}
        {[12, 13, 14, 15, 16].map((h) => (
          <b key={h} className="tabular" style={{ left: `${X(h * 60)}%` }}>
            {h}:00
          </b>
        ))}
      </div>
      <span className="film-tag">{data.policy?.label ?? "Policy pack"} · verify</span>
    </div>
  );
}

const REVENUE = [
  ["Hotels / hospitality / tourism boards", "Guests complain about heat, avoid walking, miss attractions", "Concierge widget, white-label", "Per-property monthly SaaS; tourism board = annual licence"],
  ["Delivery / micro-mobility fleets", "Rider heat stress, productivity loss, incidents", "Fleet dashboard + rider app", "Per active rider per month, or per-route API call"],
  ["Outdoor-worker employers", "Heat illness risk; UAE midday-break compliance", "Crew shift planner", "Per site per month"],
  ["Individuals", "Heat, convenience", "Free consumer app", "Free (acquisition)"],
];

function Revenue({ o }: { o: Extract<OverlayItem, { kind: "revenue" }> }) {
  return (
    <div className="film-panel film-revenue" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">Who pays · pricing hypotheses (team to validate)</span>
      <table>
        <thead>
          <tr>
            {["Segment", "Pain", "Product surface", "Pricing hypothesis", "Market size"].map((h) => (
              <th key={h} className="smallcaps">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {REVENUE.map((r, i) => (
            <tr key={r[0]} style={{ opacity: Math.min(1, Math.max(0, o.progress * 5 - i)) }}>
              <td className="font-display">{r[0]}</td>
              <td>{r[1]}</td>
              <td>{r[2]}</td>
              <td>{r[3]}</td>
              <td>{i < 3 ? <ToFill what={`market size: ${r[0]}`} /> : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FieldTest({ o, data }: { o: Extract<OverlayItem, { kind: "fieldtest" }>; data: FilmData }) {
  const c = data.meta.counts;
  const hs = (data.meta as unknown as { height_sources?: Record<string, number> }).height_sources ?? {};
  const src = data.meta.source;
  return (
    <div className="film-panel film-field" style={{ opacity: o.opacity }}>
      <span className="smallcaps film-panel-k">Data · OpenStreetMap {src?.osm_timestamp?.slice(0, 10) ?? ""}</span>
      <table className="tabular">
        <tbody>
          <tr><th>Buildings (shadow casters)</th><td>{n0(c.buildings ?? 0)}</td></tr>
          <tr><th>Heights from tags / levels / landmark</th><td>{n0((hs.tag ?? 0) + (hs.levels ?? 0) + (hs.landmark ?? 0) + (hs.part ?? 0))}</td></tr>
          <tr><th>Heights by fallback rule</th><td>{n0(hs.fallback ?? 0)}</td></tr>
          <tr><th>Walkable edges</th><td>{n0(c.edges_walk ?? 0)}</td></tr>
          <tr><th>Mapped trees</th><td>{n0(c.trees ?? 0)}</td></tr>
          <tr><th>Covered · indoor · AC-link edges</th><td>{n0(c.covered_edges ?? 0)} · {n0(c.indoor_edges ?? 0)} · {n0(c.ac_link_edges ?? 0)}</td></tr>
        </tbody>
      </table>
      <span className="smallcaps film-panel-k" style={{ marginTop: 14 }}>Field test</span>
      {data.hasFieldTest ? (
        <p className="font-display">Field readings recorded — see docs/VALIDATION.md.</p>
      ) : (
        <>
          <p className="font-display">Boulevard, 14:00 · shaded vs sunny route · result pending</p>
          <span className="film-panel-sub">IR surface + air readings <ToFill what="field test results" /></span>
        </>
      )}
    </div>
  );
}

function Roadmap({ o }: { o: Extract<OverlayItem, { kind: "roadmap" }> }) {
  const steps = ["Downtown prototype", "UAE cities", "Global open-data pipeline"];
  const gtm = [
    "Free consumer app for reach and data",
    "Hotels and tourism boards: concierge widget",
    "Delivery fleets: per-rider routing API",
    "Outdoor employers: crew shift planner",
  ];
  return (
    <>
      <div className="film-roadmap" style={{ opacity: o.opacity }}>
        {steps.map((s, i) => (
          <span key={s} className="font-display" style={{ opacity: Math.min(1, Math.max(0.15, o.progress * 4 - i)) }}>
            {s}
            {i < steps.length - 1 ? <i /> : null}
          </span>
        ))}
      </div>
      <div className="film-gtm" style={{ opacity: o.opacity * Math.min(1, Math.max(0, o.progress * 2 - 0.6)) }}>
        <span className="smallcaps film-panel-k">Go-to-market · hypotheses</span>
        <ul>
          {gtm.map((g) => (
            <li key={g}>{g}</li>
          ))}
        </ul>
      </div>
    </>
  );
}

function Closing({ o }: { o: Extract<OverlayItem, { kind: "closing" }> }) {
  return (
    <div className="film-closing" style={{ opacity: o.opacity }}>
      <p className="font-display">{closingLine()}</p>
      <span className="smallcaps" style={{ opacity: o.teamOpacity }}>
        {TEAM}
      </span>
      <span className="film-try" style={{ opacity: o.tryOpacity }}>
        Try it live <b>A</b>
      </span>
    </div>
  );
}

export function ChapterPanels({ o, data }: { o: OverlayItem; data: FilmData; frame: FrameState }) {
  switch (o.kind) {
    case "personas":
      return <Personas o={o} data={data} />;
    case "replan":
      return <Replan o={o} data={data} />;
    case "architecture":
      return <Architecture o={o} data={data} />;
    case "vignette":
      return <Vignette o={o} data={data} />;
    case "revenue":
      return <Revenue o={o} />;
    case "fieldtest":
      return <FieldTest o={o} data={data} />;
    case "roadmap":
      return <Roadmap o={o} />;
    case "closing":
      return <Closing o={o} />;
    default:
      return null;
  }
}
