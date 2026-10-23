"use client";
// Ch.7 chart (d3 scales, SVG): the departure optimiser's REAL table from hero.json. x = departure
// time (5-min steps), y = sun exposure (min), ember area, brass recommended point, hairline cursor.
// The recommendation sentence is assembled from the table's own values; when the optimiser keeps
// the requested time, the chart says so (no invented saving).
import { scaleLinear } from "d3";
import { colors } from "@/design/tokens";
import { hhmmToMinutes } from "@/lib/sun";
import type { DepartureRow, FilmData, OverlayItem } from "../types";

const W = 640;
const H = 250;
const M = { l: 46, r: 18, t: 16, b: 30 };

const minStr = (s: number) => (s / 60).toFixed(1);

export function recommendation(data: FilmData): { line: string; evidence: string | null; later: boolean } {
  const d = data.hero.departure;
  const table = d?.table ?? [];
  const rec = d?.recommended ?? table.find((r) => r.recommended);
  const req = d?.requested ?? table[0];
  if (!rec || !req) return { line: "Departure optimiser result unavailable.", evidence: null, later: false };
  if (rec.depart_time !== req.depart_time) {
    const saved = req.sun_exposure_s - rec.sun_exposure_s;
    const wait = (hhmmToMinutes(rec.depart_time) - hhmmToMinutes(req.depart_time)).toFixed(0);
    return {
      line: `Leave ${rec.depart_time} · ${minStr(saved)} min less sun · ${wait} min later`,
      evidence: null,
      later: true,
    };
  }
  const least = table.reduce<DepartureRow | null>(
    (a, r) => (r.feasible !== false && (!a || r.sun_exposure_s < a.sun_exposure_s) ? r : a),
    null,
  );
  let evidence: string | null = null;
  if (least && least.sun_exposure_s < rec.sun_exposure_s - 1) {
    const wait = hhmmToMinutes(least.depart_time) - hhmmToMinutes(rec.depart_time);
    evidence = `Waiting until ${least.depart_time} saves only ${minStr(rec.sun_exposure_s - least.sun_exposure_s)} min of sun for ${wait} min of waiting.`;
  }
  return {
    line: `Leave now: ${rec.depart_time} is already the best time for this trip.`,
    evidence,
    later: false,
  };
}

export function DepartureChart({
  o,
  data,
  minutes,
}: {
  o: Extract<OverlayItem, { kind: "chart" }>;
  data: FilmData;
  minutes: number;
}) {
  const table = data.hero.departure?.table ?? [];
  if (o.active > 0.5) return <ActivePlan o={o} data={data} />;
  if (table.length < 2)
    return (
      <div className="film-chart" style={{ opacity: o.opacity }}>
        <p className="font-display">The hero scenario has no departure table.</p>
      </div>
    );
  const xs = table.map((r) => hhmmToMinutes(r.depart_time));
  const ys = table.map((r) => r.sun_exposure_s / 60);
  const yMax = Math.max(...ys);
  const yMin = Math.min(...ys);
  const pad = Math.max(0.4, (yMax - yMin) * 0.35);
  const x = scaleLinear().domain([xs[0]!, xs[xs.length - 1]!]).range([M.l, W - M.r]);
  const y = scaleLinear()
    .domain([Math.max(0, yMin - pad), yMax + pad * 0.5])
    .range([H - M.b, M.t])
    .nice(4);
  const reveal = o.reveal;
  const nShow = Math.max(2, Math.ceil(reveal * table.length));
  const pts = table.slice(0, nShow).map((_, i) => [x(xs[i]!), y(ys[i]!)] as const);
  const line = pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
  const area = `${line}L${pts[pts.length - 1]![0].toFixed(1)},${H - M.b}L${pts[0]![0].toFixed(1)},${H - M.b}Z`;
  const recI = Math.max(0, table.findIndex((r) => r.recommended));
  const leastI = ys.indexOf(yMin);
  const cx = M.l + o.cursor * (W - M.l - M.r);
  const cm = Math.max(xs[0]!, Math.min(xs[xs.length - 1]!, minutes));
  // interpolated value at the cursor (display only)
  let ci = 0;
  while (ci < xs.length - 2 && xs[ci + 1]! <= cm) ci++;
  const fr = (cm - xs[ci]!) / Math.max(1, xs[ci + 1]! - xs[ci]!);
  const cv = ys[ci]! + (ys[ci + 1]! - ys[ci]!) * Math.min(1, Math.max(0, fr));
  const rec = recommendation(data);
  const yTicks = y.ticks(4);
  const xTicks = xs.filter((_, i) => i % 3 === 0);
  const recOp = o.rec;
  return (
    <div className="film-chart" style={{ opacity: o.opacity }}>
      <div className="film-chart-head">
        <span className="smallcaps">Sun exposure by departure time</span>
        <span className="film-badge">departure optimiser · {table.length} departures</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Sun exposure by departure time">
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} stroke="rgb(244 238 225 / 0.08)" />
            <text x={M.l - 8} y={y(v) + 4} textAnchor="end" className="film-axis">
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        {xTicks.map((v) => (
          <text key={v} x={x(v)} y={H - 8} textAnchor="middle" className="film-axis">
            {`${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`}
          </text>
        ))}
        <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} stroke="rgb(244 238 225 / 0.22)" />
        <text x={M.l} y={M.t - 4} className="film-axis">min in sun</text>
        <path d={area} fill={colors.ember} opacity={0.22} />
        <path d={line} fill="none" stroke={colors.ember} strokeWidth={1.5} />
        {leastI !== recI && nShow > leastI ? (
          <g opacity={recOp}>
            <circle cx={x(xs[leastI]!)} cy={y(ys[leastI]!)} r={4} fill="none" stroke={colors.sand} strokeWidth={1} />
            <text x={x(xs[leastI]!)} y={y(ys[leastI]!) + 18} textAnchor="middle" className="film-axis">
              least sun {table[leastI]!.depart_time}
            </text>
          </g>
        ) : null}
        {nShow > recI ? (
          <g>
            <circle cx={x(xs[recI]!)} cy={y(ys[recI]!)} r={5.5} fill={colors.brass} />
            <text x={x(xs[recI]!) + 9} y={y(ys[recI]!) - 9} className="film-axis" fill={colors.brass}>
              recommended {table[recI]!.depart_time}
            </text>
          </g>
        ) : null}
        {o.cursor > 0 ? (
          <g>
            <line x1={cx} x2={cx} y1={M.t} y2={H - M.b} stroke={colors.champagne} strokeOpacity={0.55} />
            <text x={cx + 6} y={M.t + 10} className="film-axis tabular" fill={colors.champagne}>
              {`${String(Math.floor(cm / 60)).padStart(2, "0")}:${String(Math.floor(cm % 60)).padStart(2, "0")} · ${cv.toFixed(1)} min`}
            </text>
          </g>
        ) : null}
      </svg>
      <div className="film-chart-foot">
        <div>
          <p className="font-display film-chart-rec" style={{ opacity: o.rec }}>
            {rec.line}
          </p>
          {rec.evidence ? <p className="film-chart-evidence" style={{ opacity: o.rec }}>{rec.evidence}</p> : null}
        </div>
        <button
          type="button"
          tabIndex={-1}
          className={`film-approve ${o.approve > 0.5 ? "is-pressed" : ""}`}
          style={{ transform: `scale(${1 - 0.04 * Math.sin(Math.PI * o.approve)})` }}
        >
          {o.approve > 0.5 ? "Approved" : "Approve plan"}
        </button>
      </div>
    </div>
  );
}

function ActivePlan({ o, data }: { o: Extract<OverlayItem, { kind: "chart" }>; data: FilmData }) {
  const h = data.hero;
  const c = h.coolest.stats;
  const r = data.replays.tourist_walk;
  const commit = r?.events.find((e) => e.event.type === "plan_committed")?.event.payload as
    | { summary?: { depart?: string; arrive?: string; recommendation?: string } }
    | undefined;
  const t = (iso?: string) => (iso ? iso.slice(11, 16) : null);
  const dep = t(commit?.summary?.depart) ?? h.depart;
  const arr = t(commit?.summary?.arrive);
  return (
    <div className="film-active" style={{ opacity: o.opacity }}>
      <span className="smallcaps" style={{ color: colors.oasis }}>
        Active plan
      </span>
      <p className="font-display">
        {h.origin.name} &rarr; {h.dest.name}
      </p>
      <p className="tabular film-active-stats">
        Coolest route &middot; leave {dep}
        {arr ? ` · arrive ${arr}` : ""} &middot; {(c.sun_exposure_s / 60).toFixed(1)} min in sun &middot;{" "}
        {Math.round(c.shaded_pct)}% shaded
      </p>
      <span className="film-tag">Monitor armed &middot; simulated clock</span>
    </div>
  );
}
