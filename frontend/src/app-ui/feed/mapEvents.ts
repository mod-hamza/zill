// Pure mapping from agent events to feed rows. All numbers shown come straight from the event
// payloads (verifier counts, tool_result summaries) — nothing is computed or invented here.
import { SHORT } from "@/brand";
import { colors } from "@/design/tokens";
import type { AgentEvent, FeedBadge } from "./types";

export const FRESH_MS = 1200;

export type RowKind =
  | "session"
  | "thought"
  | "tool"
  | "result"
  | "verifier"
  | "proposal"
  | "approval"
  | "message"
  | "commit"
  | "monitor"
  | "replan"
  | "error"
  | "other";

export type FeedRow = {
  key: string;
  kind: RowKind;
  marker: string;
  /** small-caps lead label (tool name, "Verifier", ...) */
  label: string;
  /** primary text */
  text: string;
  /** quieter secondary text (tool args, result summaries) */
  detail?: string;
  /** true when a tool_result reported ok: false */
  failed?: boolean;
  offsetMs: number;
};

const MARKER: Record<RowKind, string> = {
  session: colors.slate,
  thought: colors.slate,
  tool: colors.bronze,
  result: colors.bronze,
  verifier: colors.oasis,
  proposal: colors.brass,
  approval: colors.brass,
  message: colors.champagne,
  commit: colors.oasis,
  monitor: colors.slate,
  replan: colors.ember,
  error: colors.clay,
  other: colors.slate,
};

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim() ? v : undefined;
}
function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

export function prettyTool(name: string): string {
  return name.replace(/_/g, " ");
}

/** Short, human summary of tool args: scalar values only, capped. */
export function summariseArgs(args: unknown, max = 72): string {
  if (!args || typeof args !== "object") return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(args as Record<string, unknown>)) {
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean")
      parts.push(`${k} ${String(v)}`);
  }
  const s = parts.join(" · ");
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function verifierText(p: Record<string, unknown>): string {
  const checked = num(p.checked) ?? 0;
  const passed = num(p.passed) ?? 0;
  const defects = Array.isArray(p.defects) ? p.defects.length : 0;
  const base = `Verifier: ${checked} claims checked, ${passed} supported`;
  return defects > 0 ? `${base}, ${defects} flagged` : base;
}

export function offsetOf(ev: AgentEvent, first: AgentEvent | undefined, idx: number): number {
  const a = Date.parse(ev.ts);
  const b = first ? Date.parse(first.ts) : NaN;
  if (Number.isFinite(a) && Number.isFinite(b)) return Math.max(0, a - b);
  return idx * 1000;
}

export function fmtOffset(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

export function mapEvent(ev: AgentEvent, offsetMs: number, compact: boolean): FeedRow | null {
  const p = ev.payload ?? {};
  const base = { key: ev.id, offsetMs };
  const row = (kind: RowKind, label: string, text: string, extra: Partial<FeedRow> = {}): FeedRow => ({
    ...base,
    kind,
    marker: MARKER[kind],
    label,
    text,
    ...extra,
  });
  switch (ev.type) {
    case "session_started": {
      const auto = str(p.autonomy);
      return row("session", "Session", auto ? `Started, ${auto} autonomy` : "Started");
    }
    case "thought":
      return compact ? null : row("thought", "", str(p.text) ?? "");
    case "tool_call": {
      const name = prettyTool(str(p.name) ?? "tool");
      return row("tool", name, "", { detail: compact ? undefined : summariseArgs(p.args) });
    }
    case "tool_result": {
      if (compact) return null;
      const failed = p.ok === false;
      return row("result", "", str(p.summary) ?? (failed ? "Tool failed." : "Done."), {
        failed,
        marker: failed ? colors.clay : MARKER.result,
      });
    }
    case "verifier":
      return row("verifier", "", verifierText(p));
    case "proposal": {
      const routes = Array.isArray(p.routes) ? p.routes.length : 0;
      const rec = str(p.recommendation);
      return row(
        "proposal",
        "Proposal",
        rec ? `${rec} route recommended${routes ? `, ${routes} compared` : ""}` : "Plan ready",
      );
    }
    case "approval_request":
      return row("approval", "Approval", str(p.reason) ?? "Waiting for your decision");
    case "message":
      return row("message", SHORT, str(p.text) ?? "");
    case "plan_committed": {
      const auto = p.auto === true;
      return row("commit", "Committed", auto ? "Applied automatically" : "Plan committed", {
        detail: str(p.reason),
      });
    }
    case "monitor_tick": {
      const status = str(p.status);
      return row("monitor", "Monitor", str(p.note) ?? status ?? "Watching");
    }
    case "replan":
      return row("replan", "Replan", str(p.reason) ?? "Plan updated", { detail: str(p.kind) });
    case "error":
      return row("error", "Error", str(p.message) ?? "Something went wrong");
    default:
      return row("other", String(ev.type), "");
  }
}

export function mapEvents(events: AgentEvent[], compact = false): FeedRow[] {
  const first = events[0];
  const out: FeedRow[] = [];
  events.forEach((ev, i) => {
    const r = mapEvent(ev, offsetOf(ev, first, i), compact);
    if (r) out.push(r);
  });
  return out;
}

const SOURCE_LABEL: Record<FeedBadge["source"], string> = {
  live: "Live",
  recorded: "Recorded session",
  scripted: "Scripted session (live model not connected)",
};

/** Badge from events when the caller does not pass one: uses `payload.replay` from the backend. */
export function badgeFromEvents(events: AgentEvent[]): FeedBadge | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const r = events[i]?.payload?.replay;
    if (r?.source === "recorded" || r?.source === "scripted") {
      return { source: r.source, label: r.label ?? SOURCE_LABEL[r.source] };
    }
  }
  return undefined;
}

export function badgeLabel(b: FeedBadge): string {
  return b.label || SOURCE_LABEL[b.source];
}
