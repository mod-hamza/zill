"use client";
// ?debug overlay: FPS, frame time, p95, draw calls, triangles, quality tier, downgrades.
import { useStage } from "@/state/stage";

export function DebugOverlay() {
  const s = useStage();
  if (!s.debug) return null;
  return (
    <div className="tabular pointer-events-none fixed left-6 bottom-[150px] z-[55] border border-[color:var(--zill-hairline)] bg-umber/[0.92] px-3 py-2 text-[11px] leading-5 text-ivory/80">
      <div>
        {s.fps.toFixed(0)} fps &middot; {s.frameMs.toFixed(1)} ms &middot; p95{" "}
        {s.p95Ms.toFixed(1)} ms
      </div>
      <div>
        {s.drawCalls} draw calls &middot; {(s.triangles / 1e6).toFixed(2)} M
        tris
      </div>
      <div>
        tier {s.quality}
        {s.qualityForced ? " (forced)" : ""}
        {s.downgrades.length ? ` · ${s.downgrades.join(", ")}` : ""}
      </div>
    </div>
  );
}
