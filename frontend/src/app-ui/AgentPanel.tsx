"use client";
// Left-panel slot for the planning agent (chat + activity feed + autonomy) — a later phase fills
// it. Until then a quiet collapsed rail, honest about being empty.
import { useState } from "react";

export function AgentPanel() {
  const [open, setOpen] = useState(false);
  return (
    <aside className="pointer-events-auto fixed left-6 top-[104px] z-30">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="smallcaps border border-[color:var(--zill-hairline)] bg-umber/[0.92] px-3 py-2 text-sand/70 transition-colors hover:text-champagne"
        aria-expanded={open}
      >
        Agent
      </button>
      {open ? (
        <div className="mt-2 w-[300px] border border-[color:var(--zill-hairline)] bg-umber/[0.92] p-5">
          <p className="font-display text-lg font-light text-champagne">
            The planning agent sits here.
          </p>
          <p className="mt-2 text-[13px] leading-relaxed text-ivory/60">
            Chat, live activity feed and autonomy control arrive with the agent
            build. Routing below is the deterministic engine.
          </p>
        </div>
      ) : null}
    </aside>
  );
}
