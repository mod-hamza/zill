"use client";
// DOM overlays for the Film. Pure view of the current FrameState + FilmData: every number comes
// from FilmData (engine output) — this file only formats. Max 2 text elements besides the HUD.
import { ActivityFeed } from "@/app-ui/feed";
import { colors } from "@/design/tokens";
import { fmtSigned } from "@/lib/format";
import { useFilmData } from "./data";
import { DepartureChart } from "./charts/DepartureChart";
import { CHAPTERS } from "./master";
import { replayBadge, timeline } from "./replay";
import { useFilm } from "./store";
import type { FilmData, HudState, OverlayItem } from "./types";
import { ChapterPanels } from "./panels/ChapterPanels";

export function Placeholder({ what }: { what?: string }) {
  return (
    <span className="film-tofill" title={what}>
      [TEAM TO FILL — cite source]
    </span>
  );
}

const n0 = (v: number) => Math.round(v).toLocaleString("en-GB");

function Title({ o, chapter }: { o: Extract<OverlayItem, { kind: "title" }>; chapter: number }) {
  if (o.size === "hero")
    return (
      <div className="film-hero-title" style={{ opacity: o.opacity }} aria-hidden>
        <div className="font-display film-hero-name">{o.text}</div>
        {o.sub ? (
          <p className="font-display" style={{ opacity: o.subOpacity ?? 1 }}>
            {o.sub}
          </p>
        ) : null}
      </div>
    );
  return (
    <div className="film-card" style={{ opacity: o.opacity }}>
      <span className="smallcaps tabular">{String(chapter + 1).padStart(2, "0")}</span>
      <h2 className="font-display">{o.text}</h2>
    </div>
  );
}

function Caption({ o }: { o: Extract<OverlayItem, { kind: "caption" }> }) {
  return (
    <p className={`film-caption font-display ${o.align === "center" ? "is-center" : ""}`} style={{ opacity: o.opacity }}>
      {o.text}
    </p>
  );
}

function Command({ o }: { o: Extract<OverlayItem, { kind: "command" }> }) {
  return (
    <div className="film-command" style={{ opacity: o.opacity }}>
      {o.label ? <span className="smallcaps">{o.label}</span> : null}
      <div className="film-command-line">
        <span className="font-display">{o.text || " "}</span>
        <i className="film-caret" style={{ opacity: o.caret ? 1 : 0 }} />
      </div>
    </div>
  );
}

function BuildLog({ o }: { o: Extract<OverlayItem, { kind: "buildlog" }> }) {
  return (
    <div className="film-buildlog" style={{ opacity: o.opacity }}>
      <div className="film-buildlog-head">
        <span className="smallcaps">Build log</span>
        <span className="film-badge">{o.badge}</span>
      </div>
      <ol>
        {o.rows.map((r, i) => (
          <li key={i} className="film-row-in">
            <span className="smallcaps film-buildlog-step">{r.step.replace(/_/g, " ")}</span>
            <span className="film-buildlog-label">{r.label}</span>
            {r.ms !== undefined ? (
              <span className="tabular film-buildlog-ms">
                {r.ms >= 1000 ? `${(r.ms / 1000).toFixed(1)} s` : `${Math.round(r.ms)} ms`}
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Counters({ o }: { o: Extract<OverlayItem, { kind: "counters" }> }) {
  return (
    <div className="film-counters" style={{ opacity: o.opacity }}>
      {o.items.map((it) => (
        <div key={it.label}>
          <span className="font-display tabular">{n0(it.value)}</span>
          <span className="smallcaps">{it.label}</span>
        </div>
      ))}
    </div>
  );
}

const PIPE = ["OpenStreetMap", "Heights", "Shadow raster", "Exposure per street", "Time-aware routes"];
function Pipeline({ o }: { o: Extract<OverlayItem, { kind: "pipeline" }> }) {
  return (
    <div className="film-pipeline" style={{ opacity: o.opacity }}>
      <div className="film-pipeline-row">
        {PIPE.map((p, i) => {
          const a = Math.max(0, Math.min(1, o.progress * PIPE.length - i));
          return (
            <div key={p} className="film-pipeline-node" style={{ opacity: 0.25 + 0.75 * a }}>
              <span className="font-display">{p}</span>
              {i < PIPE.length - 1 ? (
                <i className="film-pipeline-link" style={{ transform: `scaleX(${a})` }} />
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="font-display film-pipeline-line">{o.line}</p>
    </div>
  );
}

const SCHEMA = ["Sun position", "Shadow cast", "Exposure per street", "Time-aware routing"];
function Schematic({ o }: { o: Extract<OverlayItem, { kind: "schematic" }> }) {
  return (
    <div className="film-schematic" style={{ opacity: o.opacity }}>
      {SCHEMA.map((p, i) => {
        const a = Math.max(0, Math.min(1, o.progress * SCHEMA.length - i));
        return (
          <div key={p} className="film-schematic-node" style={{ opacity: 0.2 + 0.8 * a }}>
            <span className="tabular smallcaps">{i + 1}</span>
            <span className="font-display">{p}</span>
          </div>
        );
      })}
    </div>
  );
}

function testsLine(data: FilmData): string | null {
  const t = data.tests;
  if (!t?.backend && !t?.frontend) return null;
  const b = t.backend?.passed ?? 0;
  const f = t.frontend?.passed ?? 0;
  const failed = (t.backend?.failed ?? 0) + (t.frontend?.failed ?? 0);
  return `${n0(b + f)} automated tests passing${failed ? ` · ${failed} failing` : ""} (${n0(b)} engine · ${n0(f)} frontend)`;
}

function Evidence({ o, data }: { o: Extract<OverlayItem, { kind: "evidence" }>; data: FilmData }) {
  const line = testsLine(data);
  return (
    <div className="film-evidence" style={{ opacity: o.opacity }}>
      <p className="font-display">{line ?? <Placeholder what="test results missing" />}</p>
      <span className="film-tag">{o.limits}</span>
    </div>
  );
}

function AcLink({ o }: { o: Extract<OverlayItem, { kind: "aclink" }> }) {
  const s = o.story;
  const f = s.fastest_with_links;
  return (
    <div className="film-aclink" style={{ opacity: o.opacity }}>
      <span className="smallcaps" style={{ color: colors.oasis }}>
        Air-conditioned link
      </span>
      <p className="font-display">
        {s.origin} &rarr; {s.dest}
      </p>
      {f ? (
        <p className="tabular film-aclink-stats">
          {n0(f.distance_m)} m &middot; {(f.sun_exposure_s / 60).toFixed(1)} min in sun &middot;{" "}
          {Math.round(f.indoor_pct)}% indoor
        </p>
      ) : null}
      <span className="film-tag">AC link: unverified on site</span>
    </div>
  );
}

function Feed({ o, data }: { o: Extract<OverlayItem, { kind: "feed" }>; data: FilmData }) {
  const r = data.replays[o.replayId];
  const tl = timeline(r, o.phases);
  const shown = tl.filter((x) => x.cum <= o.cursorMs).map((x) => x.event);
  return (
    <aside className={`film-feed ${o.title ? "is-compact" : ""}`} style={{ opacity: o.opacity }}>
      {o.title ? <span className="smallcaps film-feed-title">{o.title}</span> : null}
      <div className="film-feed-scroll">
        <ActivityFeed events={shown} badge={replayBadge(r)} now={o.cursorMs} />
      </div>
    </aside>
  );
}

export function Hud({ h, label, position }: { h: HudState; label?: string; position?: string }) {
  const indoor = h.cls === "indoor" || h.cls === "ac_link";
  const covered = h.cls === "covered";
  return (
    <div className={`film-hud is-${position ?? "center"}`}>
      <div className="film-hud-row">
        {label ? (
          <span className="smallcaps film-hud-label" style={{ color: label === "coolest" ? colors.brass : colors.sand }}>
            {label}
          </span>
        ) : null}
        <Stat label="In direct sun" value={(h.sunS / 60).toFixed(1)} unit="min" color={h.color ?? colors.ember} />
        <Stat label="Shade" value={String(Math.round(h.shadePct))} unit="%" />
        <Stat label="Clock" value={h.clock} />
        {h.feel !== undefined ? (
          <Stat
            label="Feels like"
            value={h.feel === null ? "—" : h.feel.toFixed(0)}
            unit={h.feel === null ? "" : "°C"}
            badge={h.feelBadge}
          />
        ) : null}
      </div>
      <span className="film-hud-chip" style={{ opacity: indoor || covered ? 1 : 0 }}>
        {indoor ? "Indoor · AC link" : "Covered"}
      </span>
    </div>
  );
}

function Stat({ label, value, unit, color, badge }: { label: string; value: string; unit?: string; color?: string; badge?: string }) {
  return (
    <div className="film-stat">
      <span className="font-display tabular film-stat-v" style={{ color: color ?? colors.champagne }}>
        {value}
        {unit ? <small>{unit}</small> : null}
      </span>
      <span className="smallcaps">{label}</span>
      {badge ? <span className="film-stat-badge">{badge}</span> : null}
    </div>
  );
}

function Compare({ o, data }: { o: Extract<OverlayItem, { kind: "compare" }>; data: FilmData }) {
  const c = data.hero.coolest.stats;
  return (
    <div className="film-compare" style={{ opacity: o.opacity }}>
      <span className="smallcaps">Coolest vs fastest &middot; {data.hero.origin.name} &rarr; {data.hero.dest.name}</span>
      <p className="font-display tabular">
        time {fmtSigned(c.added_time_s)} <i>&middot;</i> sun {fmtSigned(-c.sun_saved_s)} <i>&middot;</i> RHL{" "}
        {c.rhl_saved_pct > 0 ? "−" : "+"}
        {Math.abs(c.rhl_saved_pct).toFixed(0)}%
      </p>
    </div>
  );
}

function SplitLine({ o }: { o: Extract<OverlayItem, { kind: "splitline" }> }) {
  return (
    <div className="film-splitline" style={{ opacity: o.opacity }}>
      <i />
      <span className="smallcaps" style={{ left: "25%", color: colors.slate }}>
        {o.left}
      </span>
      <span className="smallcaps" style={{ left: "75%", color: colors.brass }}>
        {o.right}
      </span>
    </div>
  );
}

export function Overlay() {
  const frame = useFilm((s) => s.frame);
  const data = useFilmData((s) => s.data);
  const hidden = useFilm((s) => s.chromeHidden);
  if (!frame || !data) return null;
  const vis = frame.overlays.filter((o) => o.opacity > 0.002);
  const scrim = Math.max(
    0,
    ...vis
      .filter((o) => o.kind === "caption" || o.kind === "evidence" || o.kind === "counters" || o.kind === "closing")
      .map((o) => o.opacity),
  );
  return (
    <div className="film-overlay" data-chapter={CHAPTERS[frame.chapter]?.id}>
      <div className="film-scrim" style={{ opacity: scrim }} />
      {vis.map((o, i) => {
        const k = `${o.kind}-${i}`;
        switch (o.kind) {
          case "title":
            return <Title key={k} o={o} chapter={frame.chapter} />;
          case "caption":
            return <Caption key={k} o={o} />;
          case "command":
            return <Command key={k} o={o} />;
          case "buildlog":
            return <BuildLog key={k} o={o} />;
          case "counters":
            return <Counters key={k} o={o} />;
          case "pipeline":
            return <Pipeline key={k} o={o} />;
          case "schematic":
            return <Schematic key={k} o={o} />;
          case "evidence":
            return <Evidence key={k} o={o} data={data} />;
          case "aclink":
            return <AcLink key={k} o={o} />;
          case "feed":
            return <Feed key={k} o={o} data={data} />;
          case "hud":
            return (
              <div key={k} style={{ opacity: o.opacity }}>
                <Hud h={o.hud} label={o.label} position={o.position} />
              </div>
            );
          case "compare":
            return <Compare key={k} o={o} data={data} />;
          case "honest":
            return (
              <p key={k} className="film-honest" style={{ opacity: o.opacity }}>
                {o.text}
              </p>
            );
          case "chart":
            return <DepartureChart key={k} o={o} data={data} minutes={frame.sun.minutes} />;
          case "splitline":
            return <SplitLine key={k} o={o} />;
          default:
            return <ChapterPanels key={k} o={o} data={data} frame={frame} />;
        }
      })}
      <div className="film-fade" style={{ opacity: frame.fade }} />
      {hidden ? null : null}
    </div>
  );
}
