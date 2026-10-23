// Typed client for the agent endpoints (CONTRACTS change log 2026-10-22) and the P1 wedge APIs.
import type { AgentEvent, FeedBadge } from "@/app-ui/feed/types";
import type { Mode } from "./api";
import { fetchRetrying } from "./busy";
import { postSSE } from "./sseClient";

export type Persona = "tourist" | "rider" | "crew" | "daylight_seeker";
export type AutonomyLevel = 1 | 2 | 3;

export type SessionInfo = {
  session_id: string;
  mode: "live" | "replay";
  persona: Persona;
  autonomy_level: number;
  badge?: FeedBadge;
};

export type ReplayInfo = {
  scenario_id: string;
  persona: Persona | null;
  prompt: string | null;
  live: boolean;
  events: number;
  phases: string[];
  badge: FeedBadge;
};

export type AgentStatus = {
  mode: "live" | "replay";
  llm: Record<string, unknown>;
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetchRetrying(url, init);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = (await r.json()) as { detail?: { message?: string } };
      if (j?.detail?.message) msg = j.detail.message;
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

function post<T>(url: string, body: unknown): Promise<T> {
  return json<T>(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function parseAgentEvent(data: string): AgentEvent | null {
  try {
    const v = JSON.parse(data) as Partial<AgentEvent>;
    if (v && typeof v.type === "string") {
      return {
        id: typeof v.id === "string" ? v.id : `evt_${Math.random().toString(36).slice(2, 8)}`,
        ts: typeof v.ts === "string" ? v.ts : "",
        type: v.type,
        payload: (v.payload ?? {}) as AgentEvent["payload"],
      };
    }
  } catch {
    /* ignore malformed frame */
  }
  return null;
}

function streamAgent(
  url: string,
  body: unknown,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE(url, body, {
    signal,
    onMessage: (m) => {
      if (m.event !== "agent") return;
      const ev = parseAgentEvent(m.data);
      if (ev) onEvent(ev);
    },
  });
}

export type SimulateType = "delay" | "closure" | "heat_alert";

export const agentApi = {
  session: (body: {
    persona: Persona;
    city: string;
    date_id: string;
    clock?: string;
    autonomy_level: AutonomyLevel;
  }) => post<SessionInfo>("/api/agent/session", body),
  message: (
    body: { session_id: string; text: string; speed?: number },
    onEvent: (e: AgentEvent) => void,
    signal?: AbortSignal,
  ) => streamAgent("/api/agent/message", body, onEvent, signal),
  approve: (
    body: { session_id: string; plan_id?: string | null; approve: boolean; undo_token?: string | null; speed?: number },
    onEvent: (e: AgentEvent) => void,
    signal?: AbortSignal,
  ) => streamAgent("/api/agent/approve", body, onEvent, signal),
  simulate: (
    body: { session_id: string; type: SimulateType; params?: Record<string, unknown>; speed?: number },
    onEvent: (e: AgentEvent) => void,
    signal?: AbortSignal,
  ) => streamAgent("/api/agent/simulate", body, onEvent, signal),
  replays: () =>
    json<{ replays: ReplayInfo[]; live_available: boolean }>("/api/agent/replays"),
  status: () => json<AgentStatus>("/api/agent/status"),
};

// ---- P1 wedge / planner APIs ---------------------------------------------------------------
export type GazHit = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  kind?: string | null;
  node?: number | null;
};

export type PlanStopIn = {
  place: string | { poi?: string; lat?: number; lon?: number; name?: string; node?: number };
  dwell_min?: number;
  window?: string[] | null;
  fixed?: boolean;
};

export type PlanRequest = {
  city: string;
  mode: Mode;
  persona: Persona;
  start?: PlanStopIn["place"] | null;
  stops: PlanStopIn[];
  start_at: string;
  date_key?: string | null;
  reorder?: boolean;
  return_to_start?: boolean;
  policy_pack?: string | null;
  shift_window?: string[] | null;
};

// The plan response is loosely typed on the backend (dict). Narrow what the UI reads.
export type PlanLeg = Record<string, unknown>;
export type PlanResponse = {
  plan_id: string;
  order: number[];
  legs: PlanLeg[];
  breaks: Record<string, unknown>[];
  totals: Record<string, unknown>;
  items: Record<string, unknown>[];
  stops: Record<string, unknown>[];
  notes: string[];
  policy: Record<string, unknown> | null;
};

export const planApi = {
  gazetteer: (city: string, q: string, limit = 6) =>
    json<{ results: GazHit[] }>(
      `/api/gazetteer/${encodeURIComponent(city)}?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  plan: (body: PlanRequest) => post<PlanResponse>("/api/plan", body),
};
