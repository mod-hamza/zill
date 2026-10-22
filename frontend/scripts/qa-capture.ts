// Visual QA capture (PRD 18.3): boots Chromium against a running `next dev` (+ backend) and saves
// 1920x1080 stills of key App states into docs/qa/<phase>/.
//   npx tsx scripts/qa-capture.ts [--out ../docs/qa/phase6/iter1] [--fixture] [--only name,name]
//                                 [--swiftshader] [--q high|medium|low] [--base http://localhost:3000]
// Waits for window.__zillReady (city assets + current shade textures loaded + frames drawn).
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "@playwright/test";

type Shot = { name: string; query: string; settleMs?: number };

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? (process.argv[i + 1] ?? d) : d;
};
const flag = (k: string) => process.argv.includes(`--${k}`);

const BASE = arg("base", "http://localhost:3000")!;
const OUT = resolve(
  arg("out", join(__dirname, "..", "..", "docs", "qa", "phase6"))!,
);
const FIXTURE = flag("fixture");
const ONLY = arg("only")?.split(",");
const Q = arg("q", "high");
const SWIFT = flag("swiftshader");

// Camera strings: x,y,z,tx,ty,tz,fov (local metres; x east, y up, z south).
const CAM = {
  street: process.env.ZILL_QA_STREET ?? "420,1.7,525,0,230,0,40",
  alignClose: process.env.ZILL_QA_ALIGN ?? "-60,520,420,-60,0,60,30",
};

export const SHOTS: Shot[] = [
  { name: "01_app_default_hackathon_1200", query: "date=hackathon&time=1200" },
  { name: "02_app_hackathon_1600", query: "date=hackathon&time=1600" },
  {
    name: "03_summer_1330_route_presentation",
    query: "route=pois:metro_burj_khalifa,dubai_opera&date=summer&time=1330&view=presentation",
  },
  {
    name: "04_summer_1330_route_analysis",
    query: "route=pois:metro_burj_khalifa,dubai_opera&date=summer&time=1330&view=analysis",
  },
  {
    name: "05_low_aerial_hackathon_1600",
    query: "date=hackathon&time=1600&cam=aerial",
  },
  {
    name: "06_street_level_hackathon_1600",
    query: `date=hackathon&time=1600&cam=${CAM.street}`,
  },
  {
    name: "07_dusk_hackathon_1830",
    query: "date=hackathon&time=1830&cam=aerial",
  },
  {
    name: "08_align_close_hackathon_1200",
    query: `date=hackathon&time=1200&cam=${CAM.alignClose}`,
  },
  {
    name: "09_align_close_hackathon_1600",
    query: `date=hackathon&time=1600&cam=${CAM.alignClose}`,
  },
  { name: "10_golden_summer_1830", query: "date=summer&time=1830&cam=aerial" },
];

async function main() {
  mkdirSync(OUT, { recursive: true });
  const args = SWIFT
    ? [
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
        "--ignore-gpu-blocklist",
      ]
    : [
        "--use-angle=d3d11",
        "--enable-gpu",
        "--ignore-gpu-blocklist",
        "--enable-unsafe-webgpu",
      ];
  const browser = await chromium.launch({ headless: true, args });
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();
  const logs: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning")
      logs.push(`[${m.type()}] ${m.text().slice(0, 300)}`);
  });
  page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));

  const report: Record<string, unknown> = {
    base: BASE,
    gpu: SWIFT ? "swiftshader" : "angle-d3d11",
    shots: {},
  };
  for (const shot of SHOTS) {
    if (ONLY && !ONLY.some((o) => shot.name.includes(o))) continue;
    const url = `${BASE}/app?qa=1&debug=1&q=${Q}${FIXTURE ? "&fixture=1" : ""}&${shot.query}`;
    const t0 = Date.now();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 180_000 });
    try {
      await page.waitForFunction(() => window.__zillReady === true, undefined, {
        timeout: 120_000,
        polling: 250,
      });
    } catch {
      logs.push(`[timeout] ${shot.name} never became ready`);
    }
    await page.waitForTimeout(shot.settleMs ?? 2500);
    const renderer = await page.evaluate(() => {
      const c = document.querySelector("canvas");
      const gl = c?.getContext("webgl2") as WebGL2RenderingContext | null;
      if (!gl) return "unknown";
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      return ext
        ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL))
        : String(gl.getParameter(gl.RENDERER));
    });
    const perf = await page.evaluate(() => window.__zillPerf ?? null);
    const file = join(OUT, `${shot.name}.png`);
    await page.screenshot({ path: file });
    (report.shots as Record<string, unknown>)[shot.name] = {
      url,
      ms: Date.now() - t0,
      perf,
      renderer,
    };
    console.log(
      `${shot.name}: ${Date.now() - t0} ms  ${perf ? `${perf.fps.toFixed(0)} fps, p95 ${perf.p95Ms.toFixed(1)} ms, ${perf.drawCalls} calls, tier ${perf.quality}` : ""}  [${renderer}]`,
    );
  }
  report.logs = logs.slice(0, 200);
  writeFileSync(
    join(OUT, "capture_report.json"),
    JSON.stringify(report, null, 2),
  );
  if (logs.length)
    console.log(
      `${logs.length} console warnings/errors (see capture_report.json)`,
    );
  await browser.close();
}

void main();
