"use client";
// Left-hand planning agent (PRD 11.3, 11.5, 15): chat, streamed activity feed, route cards,
// approvals, autonomy, persona and simulated events. Replay mode is badged truthfully.
import { useEffect, useMemo, useRef, useState } from "react";
import { colors } from "@/design/tokens";
import type { AutonomyLevel, Persona, SimulateType } from "@/lib/agentApi";
import { fmtMin, fmtPct } from "@/lib/format";
import { bestColor, bestLabel } from "@/lib/preference";
import { useRoute, type RouteKey } from "@/state/route";
import { badgeOf, useAgent } from "@/state/useAgent";
import { ActivityFeed, SourceBadge } from "../feed";
import type { AgentEvent } from "../feed/types";
import { ReplanCard } from "./ReplanCard";

const PERSONAS: { id: Persona; label: string }[] = [
  { id: "tourist", label: "Tourist" },
  { id: "rider", label: "Rider" },
  { id: "crew", label: "Crew" },
];

const AUTONOMY: { id: AutonomyLevel; label: string; name: string; hint: string }[] = [
  { id: 1, label: "L1", name: "Advisor", hint: "Suggests only. Never commits a plan." },
  { id: 2, label: "L2", name: "Planner", hint: "Plans, then asks before committing." },
  { id: 3, label: "L3", name: "Autopilot", hint: "Applies small changes itself, with undo." },
];

const SIMS: { id: SimulateType; label: string }[] = [
  { id: "delay", label: "Delay 20 min" },
  { id: "closure", label: "Closure" },
  { id: "heat_alert", label: "Heat alert" },
];

const PERSONA_NAME: Record<Persona, string> = {
  tourist: "Tourist walk",
  rider: "Delivery rider",
  crew: "Crew shuttle",
};

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { id: T; label: string; sub?: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex border border-[color:var(--zill-hairline)]">
      {options.map((o) => (
        <button
          key={String(o.id)}
          type="button"
          onClick={() => onChange(o.id)}
          aria-pressed={value === o.id}
          className={`flex-1 px-2 py-1.5 text-[12px] tracking-wide transition-colors ${
            value === o.id ? "bg-stone text-champagne" : "text-ivory/55 hover:text-ivory/85"
          }`}
        >
          {o.label}
          {o.sub ? <span className="ml-1 text-[11px] opacity-70">{o.sub}</span> : null}
        </button>
      ))}
    </div>
  );
}

function RouteCards() {
  const result = useRoute((s) => s.result);
  const selected = useRoute((s) => s.selected);
  const setSelected = useRoute((s) => s.setSelected);
  if (!result) return null;
  const cards: { k: RouteKey; label: string; color: string }[] = [
    { k: "fastest", label: "Fastest", color: colors.slate },
    { k: "balanced", label: "Balanced", color: colors.bronze },
    { k: "coolest", label: bestLabel(result.preference), color: bestColor(result.preference) },
  ];
  return (
    <div className="my-2 border border-[color:var(--zill-hairline)]" data-testid="agent-route-cards">
      {cards.map((c) => {
        const r = result[c.k];
        if (!r) return null;
        const on = selected === c.k;
        return (
          <button
            key={c.k}
            type="button"
            onClick={() => setSelected(c.k)}
            aria-pressed={on}
            className={`flex w-full items-baseline gap-3 border-b border-[color:var(--zill-hairline)] px-3 py-2 text-left last:border-b-0 ${
              on ? "bg-stone/70" : "opacity-75 hover:opacity-100"
            }`}
          >
            <span className="inline-block h-px w-4 self-center" style={{ background: c.color, height: on ? 2 : 1 }} />
            <span className="smallcaps w-[68px] text-[11px] text-sand/80">{c.label}</span>
            <span className="tabular text-[13px] text-champagne">{fmtMin(r.stats.duration_s)} min</span>
            <span className="tabular text-[12px]" style={{ color: colors.ember }}>
              {fmtMin(r.stats.sun_exposure_s)} sun
            </span>
            <span className="tabular ml-auto text-[12px] text-ivory/60">{fmtPct(r.stats.shaded_pct)} shade</span>
          </button>
        );
      })}
    </div>
  );
}

function ApprovalCard() {
  const pending = useAgent((s) => s.pending);
  const busy = useAgent((s) => s.busy);
  const approve = useAgent((s) => s.approve);
  if (!pending) return null;
  return (
    <div
      className="my-2 border px-3 py-3"
      style={{ borderColor: `${colors.brass}88` }}
      data-testid="agent-approval"
    >
      <p className="smallcaps text-[10px]" style={{ color: colors.brass }}>
        Approval needed
      </p>
      <p className="mt-1.5 text-[13px] leading-snug text-ivory/80">{pending.reason}</p>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void approve(true)}
          className="border border-brass/70 px-4 py-1.5 text-[13px] text-champagne transition-colors hover:bg-stone disabled:opacity-40"
        >
          {pending.options.find((o) => o.id === "approve")?.label ?? "Approve"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void approve(false)}
          className="border border-[color:var(--zill-hairline)] px-4 py-1.5 text-[13px] text-ivory/60 transition-colors hover:text-ivory disabled:opacity-40"
        >
          {pending.options.find((o) => o.id === "reject")?.label ?? "Reject"}
        </button>
      </div>
    </div>
  );
}

function MessageCard({ ev }: { ev: AgentEvent }) {
  const text = typeof ev.payload.text === "string" ? ev.payload.text : "";
  return (
    <div className="my-2 border-l-2 pl-3" style={{ borderColor: colors.champagne }} data-testid="agent-message">
      <p className="font-display text-[14px] font-light leading-relaxed text-champagne">{text}</p>
    </div>
  );
}

type Block =
  | { t: "user"; text: string; key: string }
  | { t: "feed"; events: AgentEvent[]; key: string }
  | { t: "message"; ev: AgentEvent; key: string };

/** Interleave the user's turns with feed chunks and message cards, in arrival order. */
function buildBlocks(events: AgentEvent[], turns: { at: number; text: string }[]): Block[] {
  const out: Block[] = [];
  let chunk: AgentEvent[] = [];
  const flush = () => {
    if (chunk.length) out.push({ t: "feed", events: chunk, key: `f${chunk[0]!.id}` });
    chunk = [];
  };
  events.forEach((ev, i) => {
    for (const u of turns) if (u.at === i) {
      flush();
      out.push({ t: "user", text: u.text, key: `u${i}-${u.text.slice(0, 8)}` });
    }
    if (ev.type === "message") {
      flush();
      out.push({ t: "message", ev, key: `m${ev.id}` });
    } else chunk.push(ev);
  });
  flush();
  for (const u of turns) if (u.at >= events.length) out.push({ t: "user", text: u.text, key: `u${u.at}-end` });
  return out;
}

export function AgentPanel() {
  const a = useAgent();
  const { open, setOpen } = a;
  const [text, setText] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // ?agentSpeed=N speeds up recorded-session playback (QA / e2e); ?agent=1 opens the panel.
    const q = new URLSearchParams(window.location.search);
    const sp = Number(q.get("agentSpeed"));
    if (Number.isFinite(sp) && sp > 0) useAgent.setState({ speed: Math.min(sp, 20) });
    if (q.has("agent")) useAgent.getState().setOpen(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    void a.loadReplays();
    void a.ensureSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run on open only
  }, [open]);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [a.events.length, a.pending, a.replan, a.notices.length]);

  const badge = badgeOf(a.session, a.events, a.replays);
  const replayMode = a.session?.mode === "replay";
  const blocks = useMemo(() => buildBlocks(a.events, a.userTurns), [a.events, a.userTurns]);
  const chips = a.replays.filter((r) => r.persona === a.persona && r.prompt);
  const hasMonitor = !!a.replays.find((r) => r.scenario_id === a.scenarioId)?.phases.includes("monitor");
  const canSimulate = !!a.committedPlanId && !a.busy;
  const autonomy = AUTONOMY.find((x) => x.id === a.autonomy)!;

  const submit = () => {
    const t = text.trim();
    if (!t || a.busy) return;
    setText("");
    void a.send(t);
  };

  return (
    <aside className="zill-agent pointer-events-auto fixed left-6 top-[104px] z-30" data-testid="agent-panel">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="smallcaps border border-[color:var(--zill-hairline)] bg-umber/[0.92] px-3 py-2 text-sand/70 transition-colors hover:text-champagne"
        aria-expanded={open}
      >
        Agent
      </button>
      {open ? (
        <div className="zill-agent-body mt-2 flex max-h-[calc(100vh-340px)] min-h-[320px] w-[372px] flex-col border border-[color:var(--zill-hairline)] bg-umber/[0.94]">
          <div className="border-b border-[color:var(--zill-hairline)] px-4 pb-3 pt-3">
            <h2 className="font-display text-[18px] font-light text-champagne">Planning agent</h2>
            {badge ? (
              <div className="mt-1.5">
                <SourceBadge badge={badge} />
              </div>
            ) : null}
            <div className="mt-3">
              <Segmented
                label="Persona"
                value={a.persona}
                options={PERSONAS}
                onChange={(p) => a.setPersona(p)}
              />
            </div>
            <div className="mt-2">
              <Segmented
                label="Autonomy"
                value={a.autonomy}
                options={AUTONOMY.map((x) => ({ id: x.id, label: x.label, sub: x.name }))}
                onChange={(v) => a.setAutonomy(v)}
              />
              <p className="mt-1.5 text-[11px] leading-snug text-ivory/45">
                {autonomy.hint}
                {replayMode ? " Recorded sessions replay the autonomy level they were recorded with." : ""}
              </p>
            </div>
          </div>

          <div ref={scroller} className="min-h-[120px] flex-1 overflow-y-auto px-4 py-3" data-testid="agent-scroll">
            {blocks.length === 0 ? (
              <div>
                <p className="font-display text-[15px] font-light leading-relaxed text-ivory/70">
                  Ask for a journey and the agent will plan it, check its own claims, and ask before it commits.
                </p>
                {chips.length > 0 ? (
                  <div className="mt-3">
                    <p className="smallcaps text-[10px] text-sand/60">
                      {replayMode ? "Recorded prompts" : "Try"}
                    </p>
                    <div className="mt-2 flex flex-col gap-1.5">
                      {chips.map((c) => (
                        <button
                          key={c.scenario_id}
                          type="button"
                          disabled={a.busy}
                          onClick={() => void a.send(c.prompt!)}
                          className="border border-[color:var(--zill-hairline)] px-3 py-2 text-left text-[12.5px] leading-snug text-ivory/75 transition-colors hover:border-brass/50 hover:text-ivory disabled:opacity-40"
                          data-testid={`chip-${c.scenario_id}`}
                        >
                          <span className="smallcaps mr-2 text-[10px] text-sand/60">{PERSONA_NAME[a.persona]}</span>
                          {c.prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : replayMode ? (
                  <p className="mt-3 text-[12px] text-ivory/45">
                    No recorded session for this persona. Choose another persona.
                  </p>
                ) : null}
              </div>
            ) : (
              blocks.map((b) =>
                b.t === "user" ? (
                  <p
                    key={b.key}
                    className="my-2 text-right font-display text-[14px] font-light italic leading-snug text-sand/80"
                  >
                    {b.text}
                  </p>
                ) : b.t === "message" ? (
                  <MessageCard key={b.key} ev={b.ev} />
                ) : (
                  <ActivityFeed key={b.key} events={b.events} compact={false} />
                ),
              )
            )}
            {a.events.some((e) => e.type === "proposal") ? <RouteCards /> : null}
            <ApprovalCard />
            <ReplanCard />
            {a.notices.map((n, i) => (
              <p key={i} className="my-1 text-[12px] italic text-ivory/50">
                {n}
              </p>
            ))}
            {a.busy ? <p className="mt-2 text-[12px] text-ivory/45">Working&hellip;</p> : null}
            {a.error ? <p className="mt-2 text-[12px] text-clay">Agent error: {a.error}</p> : null}
          </div>

          {a.committedPlanId ? (
            <div className="border-t border-[color:var(--zill-hairline)] px-4 py-2.5">
              <p className="smallcaps text-[10px] text-sand/60">Simulated event</p>
              <div className="mt-1.5 flex gap-1.5">
                {SIMS.map((s) => {
                  const enabled = canSimulate && (!replayMode || (s.id === "delay" && hasMonitor));
                  return (
                    <button
                      key={s.id}
                      type="button"
                      disabled={!enabled}
                      title={
                        replayMode && !(s.id === "delay" && hasMonitor)
                          ? "Not in this recording"
                          : "Injects a simulated event into the monitor"
                      }
                      onClick={() => void a.simulate(s.id)}
                      className="flex-1 border border-[color:var(--zill-hairline)] px-2 py-1.5 text-[12px] text-ivory/70 transition-colors hover:border-ember/60 hover:text-champagne disabled:cursor-not-allowed disabled:opacity-30"
                      data-testid={`sim-${s.id}`}
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          <form
            className="border-t border-[color:var(--zill-hairline)] px-4 py-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Where would you like to go?"
              aria-label="Message the planning agent"
              spellCheck={false}
              disabled={a.busy}
              className="zill-command w-full border-0 border-b border-[color:var(--zill-hairline)] bg-transparent pb-1.5 font-display text-[16px] font-light text-champagne outline-none placeholder:text-champagne/40 focus:border-sand/40 disabled:opacity-50"
              data-testid="agent-input"
            />
          </form>
        </div>
      ) : null}
    </aside>
  );
}
