"use client";
// /health (PRD 17.5): a pre-demo check. Green = ready, amber = degraded but the demo still runs.
import { useEffect, useState } from "react";

type State = "ok" | "warn" | "pending";
type Row = { id: string; label: string; state: State; detail: string };

const INITIAL: Row[] = [
  ["backend", "Backend"],
  ["city", "City data"],
  ["model", "Model reachable"],
  ["replay", "Replay available"],
  ["shade", "Shade assets"],
  ["webgl", "WebGL"],
  ["fps", "Frame rate"],
].map(([id, label]) => ({ id: id!, label: label!, state: "pending" as State, detail: "checking" }));

type Health = {
  ok?: boolean;
  version?: string;
  replay?: boolean;
  llm?: { key_present?: boolean; model?: string };
  city?: { loaded?: boolean; name?: string; nodes?: number; edges?: number; buildings?: number };
  shade?: { all_present?: boolean; presets?: Record<string, boolean> };
  replay_available?: boolean;
  replay_sessions?: string[];
  agent?: { mode?: string; recordings?: number; recordings_live?: number; recordings_scripted?: number; key_present?: boolean };
};

function webglCheck(): { ok: boolean; detail: string } {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2") ?? c.getContext("webgl");
    if (!gl) return { ok: false, detail: "no WebGL context" };
    const ver = gl instanceof WebGL2RenderingContext ? "WebGL 2" : "WebGL 1";
    return { ok: true, detail: ver };
  } catch {
    return { ok: false, detail: "context creation failed" };
  }
}

function measureFps(ms: number): Promise<number> {
  return new Promise((resolve) => {
    let frames = 0;
    let start = 0;
    const tick = (t: number) => {
      if (!start) start = t;
      frames++;
      if (t - start >= ms) resolve((frames - 1) / ((t - start) / 1000));
      else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function loadPng(url: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => reject(new Error("image failed to load"));
    img.src = url;
  });
}

export default function HealthPage() {
  const [rows, setRows] = useState<Row[]>(INITIAL);
  const set = (id: string, state: State, detail: string) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, state, detail } : r)));

  useEffect(() => {
    let cancelled = false;
    const put = (id: string, state: State, detail: string) => {
      if (!cancelled) set(id, state, detail);
    };
    (async () => {
      let j: Health | null = null;
      try {
        const r = await fetch("/api/health");
        j = (await r.json()) as Health;
        put("backend", j.ok ? "ok" : "warn", `ok, v${j.version ?? "?"}`);
      } catch {
        put("backend", "warn", "unreachable");
      }
      if (j) {
        const c = j.city;
        put(
          "city",
          c?.loaded ? "ok" : "warn",
          c?.loaded ? `${c.name}: ${c.nodes} nodes, ${c.edges} edges, ${c.buildings} buildings` : "not baked",
        );
        const key = j.llm?.key_present ?? j.agent?.key_present;
        put(
          "model",
          key ? "ok" : "warn",
          key ? `key present (${j.llm?.model ?? "model"}), not called from here` : "no key: live agent off, replay only",
        );
        const n = j.agent?.recordings ?? j.replay_sessions?.length ?? 0;
        const live = j.agent?.recordings_live ?? 0;
        const scripted = j.agent?.recordings_scripted ?? 0;
        put(
          "replay",
          j.replay_available && n > 0 ? "ok" : "warn",
          j.replay_available
            ? `${n} recordings (${live} live, ${scripted} scripted)${j.replay ? ", forced on" : ""}`
            : "no recordings",
        );
      } else {
        for (const id of ["city", "model", "replay"]) put(id, "warn", "backend unreachable");
      }
      try {
        const { w, h } = await loadPng("/api/shade/dubai_downtown/summer/1330.png");
        const presets = j?.shade?.presets ? Object.values(j.shade.presets) : [];
        const all = j?.shade?.all_present !== false;
        put("shade", all ? "ok" : "warn", `summer 13:30 PNG ${w}x${h}${presets.length ? `, ${presets.filter(Boolean).length}/${presets.length} dates baked` : ""}`);
      } catch {
        put("shade", "warn", "could not load a shade PNG");
      }
      const gl = webglCheck();
      put("webgl", gl.ok ? "ok" : "warn", gl.detail);
      const fps = await measureFps(2000);
      put(
        "fps",
        fps >= 30 ? "ok" : "warn",
        `${fps.toFixed(0)} fps over 2 s${document.hidden ? " (tab hidden, unreliable)" : ""}`,
      );
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const bad = rows.filter((r) => r.state === "warn").length;
  const pending = rows.some((r) => r.state === "pending");
  return (
    <main className="mx-auto max-w-2xl px-6 py-24">
      <h1 className="font-display text-4xl font-light text-champagne">Health</h1>
      <p className="mt-3 text-sm text-ivory/55" data-testid="health-summary">
        {pending ? "Checking…" : bad === 0 ? "All checks green." : `${bad} check${bad === 1 ? "" : "s"} amber.`}
      </p>
      <ul className="mt-8 divide-y divide-ivory/10 border-y border-ivory/10">
        {rows.map((row) => (
          <li key={row.id} className="flex items-baseline gap-4 py-4" data-testid={`health-${row.id}`} data-state={row.state}>
            <span
              aria-label={row.state}
              className="inline-block h-2.5 w-2.5 shrink-0 self-center rounded-full"
              style={{
                background:
                  row.state === "ok" ? "var(--zill-oasis)" : row.state === "warn" ? "var(--zill-ember)" : "var(--zill-slate)",
              }}
            />
            <span className="w-40 shrink-0">{row.label}</span>
            <span className="tabular flex-1 text-sm text-ivory/60">{row.detail}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
