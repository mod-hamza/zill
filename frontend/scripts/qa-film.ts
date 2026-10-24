// Film visual QA (PRD 18.3): 1920x1080 stills at start / mid / end of every chapter via ?qa=1&t=,
// waiting for window.__zillFrameReady (data + city + current shade pair loaded, frame settled).
//   npx tsx scripts/qa-film.ts --out ../docs/qa/phase7/iter1 [--chapters 1-7] [--times 12.5,300]
//                              [--swiftshader] [--q high] [--base http://localhost:3000]
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "@playwright/test";
import { CHAPTER_STARTS, CHAPTERS, setCut } from "../src/film/master";

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? (process.argv[i + 1] ?? d) : d;
};
const flag = (k: string) => process.argv.includes(`--${k}`);
const BASE = arg("base", "http://localhost:3000")!;
const OUT = resolve(arg("out", join(__dirname, "..", "..", "docs", "qa", "phase7", "iter1"))!);
const Q = arg("q", "high");
// --cut short (default: /film) | full (/film2)
const CUT = arg("cut", "short") === "full" ? "full" : "short";
setCut(CUT);
const FILM_PATH = CUT === "full" ? "/film2" : "/film";
const SWIFT = flag("swiftshader");
const [c0, c1] = (arg("chapters", "1-15")!.split("-").map(Number) as [number, number?]);
const EXTRA = arg("times")?.split(",").map(Number).filter((x) => Number.isFinite(x)) ?? [];
const POINTS = (arg("points", "start,mid,end")!).split(",");

type Shot = { name: string; t: number };
const shots: Shot[] = [];
if (!flag("only-times")) {
  CHAPTERS.forEach((c, i) => {
    const n = i + 1;
    if (n < c0 || n > (c1 ?? c0)) return;
    const s = CHAPTER_STARTS[i]!;
    const pts: Record<string, number> = {
      start: s + Math.min(6, c.dur_s * 0.12),
      mid: s + c.dur_s * 0.5,
      end: s + c.dur_s - 2.5,
    };
    for (const p of POINTS)
      if (pts[p] !== undefined) shots.push({ name: `ch${String(n).padStart(2, "0")}_${p}`, t: pts[p]! });
  });
}
for (const t of EXTRA) shots.push({ name: `t_${t.toFixed(1).padStart(6, "0")}`, t });

async function main() {
  mkdirSync(OUT, { recursive: true });
  const args = SWIFT
    ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    : ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"];
  const browser = await chromium.launch({ headless: true, args });
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const logs: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") logs.push(`[${m.type()}] ${m.text().slice(0, 300)}`);
  });
  page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));
  const first = shots[0]?.t ?? 0;
  await page.goto(`${BASE}${FILM_PATH}?qa=1&q=${Q}&t=${first}`, { waitUntil: "domcontentloaded", timeout: 180_000 });
  const report: Record<string, unknown> = { base: BASE, gpu: SWIFT ? "swiftshader" : "angle-d3d11", shots: {} };
  for (const s of shots) {
    const t0 = Date.now();
    await page.evaluate((t) => (window as unknown as { __zillFilmSetT?: (x: number) => void }).__zillFilmSetT?.(t), s.t);
    await page.waitForTimeout(150);
    try {
      await page.waitForFunction(() => window.__zillFrameReady === true, undefined, { timeout: 120_000, polling: 100 });
    } catch {
      logs.push(`[timeout] ${s.name} never became ready`);
    }
    await page.waitForTimeout(700);
    const file = join(OUT, `${s.name}.png`);
    await page.screenshot({ path: file });
    const perf = await page.evaluate(() => window.__zillPerf ?? null);
    (report.shots as Record<string, unknown>)[s.name] = { t: s.t, ms: Date.now() - t0, perf };
    console.log(`${s.name} t=${s.t.toFixed(1)}  ${Date.now() - t0} ms`);
  }
  report.logs = logs.slice(0, 200);
  writeFileSync(join(OUT, "capture_report.json"), JSON.stringify(report, null, 2));
  if (logs.length) console.log(`${logs.length} console warnings/errors:\n${logs.slice(0, 15).join("\n")}`);
  await browser.close();
}
void main();
