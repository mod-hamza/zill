"use client";

import { useEffect, useState } from "react";

type Row = { label: string; state: "ok" | "warn"; detail: string };

export default function HealthPage() {
  const [rows, setRows] = useState<Row[]>([{ label: "Backend", state: "warn", detail: "checking" }]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next: Row[] = [];
      try {
        const r = await fetch("/api/health");
        const j = await r.json();
        next.push({ label: "Backend", state: j.ok ? "ok" : "warn", detail: `v${j.version}` });
        next.push({
          label: "Model key",
          state: j.llm?.key_present ? "ok" : "warn",
          detail: j.llm?.key_present ? String(j.llm.model) : "no key, replay only",
        });
        next.push({ label: "Replay mode", state: "ok", detail: j.replay ? "forced on" : "available" });
      } catch {
        next.push({ label: "Backend", state: "warn", detail: "unreachable" });
      }
      let webgl = false;
      try {
        webgl = !!document.createElement("canvas").getContext("webgl2");
      } catch {
        webgl = false;
      }
      next.push({ label: "WebGL", state: webgl ? "ok" : "warn", detail: webgl ? "webgl2" : "unavailable" });
      if (!cancelled) setRows(next);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-xl px-6 py-24">
      <h1 className="font-display text-4xl font-light text-champagne">Health</h1>
      <ul className="mt-10 divide-y divide-ivory/10 border-y border-ivory/10">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center gap-4 py-4">
            <span
              aria-label={row.state}
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: row.state === "ok" ? "var(--zill-oasis)" : "var(--zill-ember)" }}
            />
            <span className="flex-1">{row.label}</span>
            <span className="tabular text-sm text-ivory/60">{row.detail}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
