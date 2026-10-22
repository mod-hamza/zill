"use client";
// Refined loading screen (PRD 13.3): serif line + thin brass progress hairline. No spinners.
import { useEffect, useState } from "react";
import { useCity } from "@/state/city";
import { useStage } from "@/state/stage";

export function LoadingScreen() {
  const progress = useCity((s) => s.progress);
  const loaded = useCity((s) => s.loaded);
  const error = useCity((s) => s.error);
  const meta = useCity((s) => s.meta);
  const shadeReady = useStage((s) => s.shadeReady);
  const done = loaded && shadeReady;
  const [gone, setGone] = useState(false);

  useEffect(() => {
    if (!done) return;
    const id = window.setTimeout(() => setGone(true), 900);
    return () => window.clearTimeout(id);
  }, [done]);

  if (gone) return null;
  const name = meta && !meta.synthetic ? meta.name : "Downtown Dubai";
  return (
    <div
      className="zill-loading fixed inset-0 z-[60] flex flex-col items-center justify-center bg-ink"
      style={{ opacity: done ? 0 : 1 }}
      aria-busy={!done}
    >
      <p
        className="font-display text-champagne"
        style={{ fontWeight: 300, fontSize: "clamp(1.6rem, 2.4vw, 2.4rem)" }}
      >
        Preparing {name}&hellip;
      </p>
      <div className="mt-6 h-px w-64 bg-[color:var(--zill-hairline)]">
        <div
          className="h-px bg-brass"
          style={{
            width: `${Math.round(Math.max(0.02, done ? 1 : progress * 0.97) * 100)}%`,
            transition: "width 400ms var(--zill-ease)",
          }}
        />
      </div>
      {error ? (
        <p className="mt-6 max-w-md text-center text-[13px] text-ivory/60">
          The city data could not be loaded ({error}). Start the backend with{" "}
          <span className="text-sand">python scripts/zill.py dev</span> and
          reload.
        </p>
      ) : null}
    </div>
  );
}
