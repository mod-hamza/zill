// Agent SSE event shapes (CONTRACTS section 7 + change log). Shared by the App agent panel and
// the Film (which replays recorded events through <ActivityFeed>).

export type AgentEventType =
  | "session_started"
  | "thought"
  | "tool_call"
  | "tool_result"
  | "verifier"
  | "proposal"
  | "approval_request"
  | "message"
  | "plan_committed"
  | "monitor_tick"
  | "replan"
  | "error"
  | (string & {});

export type FeedSource = "live" | "recorded" | "scripted";

export type FeedBadge = { source: FeedSource; label: string };

/** `payload.replay` is attached by the backend replay player (CONTRACTS change log). */
export type ReplayInfo = {
  source?: string;
  label?: string;
  scenario_id?: string;
  phase?: string;
};

export type AgentEvent = {
  id: string;
  ts: string;
  type: AgentEventType;
  // Payload shape depends on `type`; narrowed in feed/mapEvents.ts, never trusted blindly.
  payload: Record<string, unknown> & { replay?: ReplayInfo };
};

export type FeedProps = {
  events: AgentEvent[];
  badge?: FeedBadge;
  /** one tight line per event, thoughts and result summaries hidden */
  compact?: boolean;
  /**
   * Optional reference clock in ms since the first event. Purely presentational: rows whose
   * offset is within FRESH_MS of `now` are emphasised. It never hides or reveals events — the
   * caller (the Film) decides which events are passed in.
   */
  now?: number;
};
