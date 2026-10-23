// useAgent: the planning agent session — streamed events, pending approval, replan + undo.
// Replay mode (no live model) is detected from the session response and badged truthfully.
import { create } from "zustand";
import { buildAgentRoutes } from "@/app-ui/agent/applyRoutes";
import type { AgentEvent, FeedBadge } from "@/app-ui/feed/types";
import {
  agentApi,
  type AutonomyLevel,
  type Persona,
  type ReplayInfo,
  type SessionInfo,
  type SimulateType,
} from "@/lib/agentApi";
import type { RouteResponse } from "@/lib/api";
import { minutesToHHMM } from "@/lib/sun";
import { frameRouteView } from "@/three/AppDrivers";
import { useCity } from "./city";
import { useRig } from "./rig";
import { useRoute } from "./route";
import { PRESET_DATES, useSun } from "./sun";

export type PendingApproval = {
  planId: string;
  reason: string;
  risk: string;
  options: { id: string; label: string }[];
};

export type ReplanInfo = {
  kind: string;
  reason: string;
  auto: boolean;
  newPlanId: string | null;
  diff: Record<string, unknown>;
  undoToken: string | null;
  undone: boolean;
};

type AgentState = {
  open: boolean;
  persona: Persona;
  autonomy: AutonomyLevel;
  session: SessionInfo | null;
  events: AgentEvent[];
  busy: boolean;
  error: string | null;
  pending: PendingApproval | null;
  committedPlanId: string | null;
  replan: ReplanInfo | null;
  replays: ReplayInfo[];
  liveAvailable: boolean;
  /** scenario id of the recording currently playing (replay mode only) */
  scenarioId: string | null;
  /** routes to restore on a local undo (replay mode) */
  previousResult: RouteResponse | null;
  /** UI-local notices (not agent output) */
  notices: string[];
  /** the user's own turns: `at` = number of events received before it was sent */
  userTurns: { at: number; text: string }[];
  /** playback speed multiplier for recorded sessions */
  speed: number;
  setOpen: (o: boolean) => void;
  setPersona: (p: Persona) => void;
  setAutonomy: (a: AutonomyLevel) => void;
  loadReplays: () => Promise<void>;
  ensureSession: (force?: boolean) => Promise<SessionInfo | null>;
  send: (text: string) => Promise<void>;
  approve: (approve: boolean) => Promise<void>;
  simulate: (type: SimulateType) => Promise<void>;
  undo: () => Promise<void>;
  reset: () => void;
};

let abort: AbortController | null = null;
let eventSeq = 0;

function dateKeyFor(iso: string): string {
  const hit = Object.entries(PRESET_DATES).find(([, v]) => v === iso);
  return hit ? hit[0] : iso;
}

function applyToScene(routes: unknown, tokens: Record<string, unknown> | undefined, dateKey: string) {
  const cur = useRoute.getState();
  const built = buildAgentRoutes(routes, tokens, dateKey, { a: cur.a?.name, b: cur.b?.name });
  if (!built) return false;
  const sun = useSun.getState();
  if (built.dateIso) sun.setDate(dateKeyFor(built.dateIso), built.dateIso);
  if (built.departMinutes !== null) sun.setMinutes(built.departMinutes);
  useRoute.setState({
    a: built.a,
    b: built.b,
    mode: built.response.coolest.mode,
    result: built.response,
    selected: "coolest",
    activeScenario: null,
    error: null,
    flyT: null,
  });
  useRig.getState().setView(frameRouteView(built.response.coolest));
  return true;
}

export const useAgent = create<AgentState>((set, get) => {
  const ingest = (ev: AgentEvent) => {
    const id = `${ev.id}#${eventSeq++}`;
    const stored = { ...ev, id };
    set((s) => ({ events: [...s.events, stored] }));
    const p = ev.payload;
    const rep = p.replay;
    if (rep?.scenario_id && get().scenarioId !== rep.scenario_id) set({ scenarioId: rep.scenario_id });
    const dateKey = useSun.getState().dateKey;
    switch (ev.type) {
      case "proposal": {
        const prev = useRoute.getState().result;
        set({ previousResult: prev });
        applyToScene(p.routes, p.tokens as Record<string, unknown> | undefined, dateKey);
        break;
      }
      case "approval_request":
        set({
          pending: {
            planId: String(p.plan_id ?? ""),
            reason: typeof p.reason === "string" ? p.reason : "",
            risk: typeof p.risk === "string" ? p.risk : "",
            options: Array.isArray(p.options)
              ? (p.options as { id: string; label: string }[])
              : [
                  { id: "approve", label: "Approve plan" },
                  { id: "reject", label: "Not now" },
                ],
          },
        });
        break;
      case "plan_committed": {
        const token = typeof p.undo_token === "string" ? p.undo_token : null;
        set((s) => ({
          pending: null,
          committedPlanId: String(p.plan_id ?? ""),
          replan: token && s.replan ? { ...s.replan, undoToken: token } : s.replan,
        }));
        break;
      }
      case "replan": {
        const prev = useRoute.getState().result;
        set({
          previousResult: prev,
          replan: {
            kind: String(p.kind ?? "replan"),
            reason: typeof p.reason === "string" ? p.reason : "",
            auto: p.auto === true,
            newPlanId: typeof p.new_plan_id === "string" ? p.new_plan_id : null,
            diff: (p.diff ?? {}) as Record<string, unknown>,
            undoToken: null,
            undone: false,
          },
        });
        applyToScene(p.routes, undefined, dateKey);
        break;
      }
      default:
        break;
    }
  };

  const run = async (fn: (signal: AbortSignal) => Promise<void>) => {
    abort?.abort();
    const ac = new AbortController();
    abort = ac;
    set({ busy: true, error: null });
    try {
      await fn(ac.signal);
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError")
        set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      if (abort === ac) set({ busy: false });
    }
  };

  return {
    open: false,
    persona: "tourist",
    autonomy: 2,
    session: null,
    events: [],
    busy: false,
    error: null,
    pending: null,
    committedPlanId: null,
    replan: null,
    replays: [],
    liveAvailable: false,
    scenarioId: null,
    previousResult: null,
    notices: [],
    userTurns: [],
    speed: 1,
    setOpen: (open) => set({ open }),
    setPersona: (persona) => {
      set({ persona });
      get().reset();
    },
    setAutonomy: (autonomy) => {
      set({ autonomy });
      get().reset();
    },
    loadReplays: async () => {
      try {
        const j = await agentApi.replays();
        set({ replays: j.replays, liveAvailable: j.live_available });
      } catch (e) {
        set({ error: e instanceof Error ? e.message : String(e) });
      }
    },
    ensureSession: async (force = false) => {
      const cur = get().session;
      if (cur && !force) return cur;
      try {
        const sun = useSun.getState();
        const s = await agentApi.session({
          persona: get().persona,
          city: useCity.getState().cityId,
          date_id: sun.dateKey,
          clock: minutesToHHMM(sun.minutes, ":"),
          autonomy_level: get().autonomy,
        });
        set({ session: s, error: null });
        return s;
      } catch (e) {
        set({ error: e instanceof Error ? e.message : String(e) });
        return null;
      }
    },
    send: async (text) => {
      const t = text.trim();
      if (!t) return;
      const s = await get().ensureSession();
      if (!s) return;
      set((st) => ({
        pending: null,
        replan: null,
        scenarioId: null,
        userTurns: [...st.userTurns, { at: st.events.length, text: t }],
      }));
      await run((signal) =>
        agentApi.message({ session_id: s.session_id, text: t, speed: get().speed }, ingest, signal),
      );
    },
    approve: async (approve) => {
      const s = get().session;
      const pend = get().pending;
      if (!s || !pend) return;
      if (!approve && s.mode === "replay") {
        // The recording has no "reject" branch; decline locally rather than fake an agent reply.
        set((st) => ({
          pending: null,
          notices: [...st.notices, "Plan not approved. Nothing was committed."],
        }));
        return;
      }
      set({ pending: null });
      await run((signal) =>
        agentApi.approve(
          { session_id: s.session_id, plan_id: pend.planId, approve, speed: get().speed },
          ingest,
          signal,
        ),
      );
    },
    simulate: async (type) => {
      const s = get().session;
      if (!s) return;
      await run((signal) =>
        agentApi.simulate(
          {
            session_id: s.session_id,
            type,
            params: type === "delay" ? { minutes: 20 } : {},
            speed: get().speed,
          },
          ingest,
          signal,
        ),
      );
    },
    undo: async () => {
      const s = get().session;
      const rp = get().replan;
      if (!s || !rp) return;
      if (s.mode === "replay") {
        // Recorded sessions cannot execute an undo; revert the view locally and say so.
        const prev = get().previousResult;
        if (prev) {
          useRoute.setState({ result: prev, selected: "coolest" });
          useRig.getState().setView(frameRouteView(prev.coolest));
        }
        set((st) => ({
          replan: st.replan ? { ...st.replan, undone: true } : null,
          notices: [...st.notices, "Reverted the view to the previous plan (recorded session, not executed)."],
        }));
        return;
      }
      if (!rp.undoToken) return;
      await run((signal) =>
        agentApi.approve(
          { session_id: s.session_id, approve: true, undo_token: rp.undoToken, speed: get().speed },
          ingest,
          signal,
        ),
      );
      set((st) => ({ replan: st.replan ? { ...st.replan, undone: true } : null }));
    },
    reset: () => {
      abort?.abort();
      set({
        session: null,
        events: [],
        pending: null,
        committedPlanId: null,
        replan: null,
        scenarioId: null,
        previousResult: null,
        notices: [],
        userTurns: [],
        busy: false,
        error: null,
      });
    },
  };
});

export function badgeOf(
  session: SessionInfo | null,
  events: AgentEvent[],
  replays: ReplayInfo[],
): FeedBadge | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const r = events[i]?.payload.replay;
    if (r?.source === "recorded" || r?.source === "scripted")
      return { source: r.source, label: r.label ?? "Recorded session" };
  }
  if (!session) return undefined;
  if (session.mode === "live") return { source: "live", label: "Live" };
  // Replay mode before any event: describe what the recordings really are.
  if (replays.length > 0 && replays.every((r) => !r.live))
    return { source: "scripted", label: "Scripted session (live model not connected)" };
  return session.badge;
}
