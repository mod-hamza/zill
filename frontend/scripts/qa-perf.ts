// Perf probe (PRD 18.4 style): per quality tier, slowly orbits the default view for N seconds and
// reports mean FPS, mean / p95 frame time and draw calls from window.__zillPerf.
//   npx tsx scripts/qa-perf.ts [--seconds 8]
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "@playwright/test";

const secs = Number(process.argv[process.argv.indexOf("--seconds") + 1]) || 8;

void (async () => {
  const b = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--disable-gpu-vsync", "--disable-frame-rate-limit"] });
  const out: Record<string, unknown> = {};
  for (const q of ["high", "medium", "low"]) {
    const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
    await p.goto(`http://localhost:3000/app?qa=1&q=${q}&date=hackathon&time=1600`, { timeout: 180000 });
    await p.waitForFunction(() => (window as unknown as { __zillReady?: boolean }).__zillReady === true, undefined, { timeout: 120000 });
    // scrub time continuously while measuring (exercises shade texture blending + light)
    // (string-evaluated: tsx would inject helpers into serialized functions)
    await p.evaluate(`(() => { const z = window.__zill; const t0 = performance.now();
      const tick = () => { const el = (performance.now() - t0) / 1000;
        z.useSun.getState().setMinutes(14 * 60 + el * 20); if (el < ${secs} + 3) requestAnimationFrame(tick); };
      tick(); })()`);
    await p.waitForTimeout(3000);
    const frames = (await p.evaluate(`new Promise((res) => { const ts = []; const t0 = performance.now();
      const f = (t) => { ts.push(t); if (t - t0 < ${secs} * 1000) requestAnimationFrame(f); else res(ts); };
      requestAnimationFrame(f); })`)) as number[];
    const d = frames.slice(1).map((t, i) => t - frames[i]!).sort((a, b2) => a - b2);
    const mean = d.reduce((a, b2) => a + b2, 0) / d.length;
    const perf = await p.evaluate("window.__zillPerf");
    out[q] = { fps: +(1000 / mean).toFixed(1), meanMs: +mean.toFixed(2), p95Ms: +d[Math.floor(d.length * 0.95)]!.toFixed(2), frames: d.length, perf };
    console.log(q, JSON.stringify(out[q]));
    await p.close();
  }
  writeFileSync(join(__dirname, "..", "..", "docs", "qa", "phase6", "perf.json"), JSON.stringify(out, null, 2));
  await b.close();
})();
