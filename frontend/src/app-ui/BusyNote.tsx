"use client";
// Calm rate-limit notice: shown while the client waits out a 429 Retry-After before retrying.
import { useEffect, useState } from "react";
import { useBusy } from "@/lib/busy";

export function BusyNote() {
  const until = useBusy((s) => s.until);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until === null) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [until]);
  if (until === null) return null;
  const s = Math.max(1, Math.ceil((until - now) / 1000));
  return (
    <p
      className="zill-busy pointer-events-none fixed left-1/2 z-40 -translate-x-1/2 border border-[color:var(--zill-hairline)] bg-umber/[0.92] px-3 py-1 text-[12px] tracking-wide text-sand/80"
      role="status"
      aria-live="polite"
      data-testid="busy-note"
    >
      Busy, retrying in {s}&nbsp;s
    </p>
  );
}
