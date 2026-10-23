// Recorded/scripted agent sessions as a deterministic timeline (cumulative dt_ms per event).
import type { AgentEvent, FeedBadge } from "@/app-ui/feed";
import type { Replay } from "./types";

export type TimedEvent = { cum: number; phase: string; event: AgentEvent };

const BASE = Date.parse("2026-07-15T00:00:00Z");

/** Events of the given phases with cumulative times (ms from the first kept event). */
export function timeline(r: Replay | undefined, phases?: string[]): TimedEvent[] {
  if (!r) return [];
  const out: TimedEvent[] = [];
  let cum = 0;
  let first = true;
  for (const it of r.events) {
    const ph = it.phase ?? "plan";
    if (phases && !phases.includes(ph)) continue;
    cum += first ? 0 : it.dt_ms;
    first = false;
    out.push({
      cum,
      phase: ph,
      // stable ids + synthetic timestamps so <ActivityFeed> offsets equal the recording's dt
      event: { ...it.event, id: it.event.id ?? `${r.scenario_id}_${out.length}`, ts: new Date(BASE + cum).toISOString() },
    });
  }
  return out;
}

export function totalMs(tl: TimedEvent[]): number {
  return tl.length ? tl[tl.length - 1]!.cum : 0;
}

/** cumulative ms at which the first event matching `pred` happens (or null) */
export function cumOf(tl: TimedEvent[], pred: (e: AgentEvent) => boolean): number | null {
  const e = tl.find((x) => pred(x.event));
  return e ? e.cum : null;
}

/** Truthful badge (CONTRACTS 7): live:true -> "Recorded session", else scripted. */
export function replayBadge(r: Replay | undefined): FeedBadge {
  if (r?.live) return { source: "recorded", label: "Recorded session" };
  return { source: "scripted", label: "Scripted session — live model not connected" };
}

export function payloadOf<T = Record<string, unknown>>(tl: TimedEvent[], type: string): T | null {
  const e = tl.find((x) => x.event.type === type);
  return e ? (e.event.payload as unknown as T) : null;
}
