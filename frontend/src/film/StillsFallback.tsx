"use client";
// PRD 17.4: if WebGL is unavailable or the context is lost, /film degrades to the chapter stills
// exported by scripts/export-deck-assets.ts (public/stills/manifest.json), ←/→ to navigate.
import { useEffect, useState } from "react";

type Still = { file: string; chapter: number; title: string };

export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function StillsFallback() {
  const [stills, setStills] = useState<Still[] | null>(null);
  const [i, setI] = useState(0);
  useEffect(() => {
    fetch("/stills/manifest.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((j: { stills?: Still[] } | null) => setStills(j?.stills ?? []))
      .catch(() => setStills([]));
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const n = stills?.length ?? 0;
      if (!n) return;
      if (e.key === "ArrowRight") setI((x) => Math.min(n - 1, x + 1));
      if (e.key === "ArrowLeft") setI((x) => Math.max(0, x - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stills]);
  const s = stills?.[i];
  return (
    <div className="film-stills">
      {s ? (
        // eslint-disable-next-line @next/next/no-img-element -- static exported stills, no optimisation needed
        <img src={`/stills/${s.file}`} alt={s.title} />
      ) : null}
      <div className="film-stills-bar">
        <span className="smallcaps tabular">
          {s ? String(s.chapter).padStart(2, "0") : "--"}
        </span>
        <span className="font-display">{s?.title ?? (stills ? "No stills exported yet" : "Loading stills…")}</span>
        <span className="film-tag">3D unavailable · stills</span>
      </div>
    </div>
  );
}
