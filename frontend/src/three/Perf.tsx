"use client";
// Frame-time monitor: rolling FPS / p95 / draw calls, auto-downgrade (PRD 13.3: rolling frame
// time > 22 ms for 2 s -> step the quality tier down), WebGL context-loss handling, readiness
// flag for QA captures (window.__zillReady).
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { useCity } from "@/state/city";
import { useStage, type Quality } from "@/state/stage";

declare global {
  interface Window {
    __zillReady?: boolean;
    __zillPerf?: {
      fps: number;
      frameMs: number;
      p95Ms: number;
      drawCalls: number;
      triangles: number;
      quality: Quality;
    };
  }
}

const DOWN: Record<Quality, Quality | null> = {
  high: "medium",
  medium: "low",
  low: null,
};

export function Perf() {
  const gl = useThree((s) => s.gl);
  const samples = useRef<number[]>([]);
  const slowSince = useRef<number | null>(null);
  const acc = useRef({ t: 0, frames: 0 });
  const readyFrames = useRef(0);
  const calls = useRef({ calls: 0, tris: 0 });

  useEffect(() => {
    gl.info.autoReset = false;
    const canvas = gl.domElement;
    const lost = (e: Event) => {
      e.preventDefault();
      useStage.getState().setContextLost(true);
    };
    const restored = () => useStage.getState().setContextLost(false);
    canvas.addEventListener("webglcontextlost", lost);
    canvas.addEventListener("webglcontextrestored", restored);
    return () => {
      canvas.removeEventListener("webglcontextlost", lost);
      canvas.removeEventListener("webglcontextrestored", restored);
    };
  }, [gl]);

  // first in the frame: reset render counters (the composer renders several passes per frame)
  useFrame(() => {
    gl.info.reset();
  }, -1000);

  // after the composer (priority 1): read counters, update stats
  useFrame((_, delta) => {
    calls.current = {
      calls: gl.info.render.calls,
      tris: gl.info.render.triangles,
    };
    const ms = delta * 1000;
    const st = useStage.getState();
    if (!document.hidden) {
      samples.current.push(ms);
      if (samples.current.length > 240) samples.current.shift();
    }
    acc.current.t += delta;
    acc.current.frames += 1;
    if (acc.current.t >= 0.5) {
      const s = [...samples.current].sort((a, b) => a - b);
      const p95 = s[Math.floor(s.length * 0.95)] ?? ms;
      const mean = s.reduce((a, b) => a + b, 0) / Math.max(1, s.length);
      const fps = acc.current.frames / acc.current.t;
      st.setPerf({
        fps,
        frameMs: mean,
        p95Ms: p95,
        drawCalls: calls.current.calls,
        triangles: calls.current.tris,
      });
      window.__zillPerf = {
        fps,
        frameMs: mean,
        p95Ms: p95,
        drawCalls: calls.current.calls,
        triangles: calls.current.tris,
        quality: st.quality,
      };
      acc.current = { t: 0, frames: 0 };
      // auto-downgrade
      const recent = samples.current.slice(-60);
      const recentMean =
        recent.reduce((a, b) => a + b, 0) / Math.max(1, recent.length);
      const now = performance.now();
      if (
        !st.qualityForced &&
        !st.qa &&
        !document.hidden &&
        recent.length >= 30 &&
        recentMean > 22
      ) {
        if (slowSince.current === null) slowSince.current = now;
        else if (now - slowSince.current > 2000) {
          const next = DOWN[st.quality];
          if (next) {
            st.noteDowngrade(
              `${st.quality}->${next} at ${recentMean.toFixed(1)} ms`,
            );
            st.setQuality(next);
            samples.current = [];
          }
          slowSince.current = null;
        }
      } else slowSince.current = null;
    }
    // readiness for QA captures: assets loaded + current shade pair loaded + a few frames drawn
    const ready = useCity.getState().loaded && st.shadeReady;
    readyFrames.current = ready ? readyFrames.current + 1 : 0;
    window.__zillReady = readyFrames.current > 8;
  }, 2);

  return null;
}
