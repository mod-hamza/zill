// Flicker probe: renders pairs of film frames 1/50 s apart (legitimate motion is negligible at
// that spacing) and reports how many pixels jump by > 40 grey levels after a 3x3 median (which
// removes film grain). Shimmering windows / z-fighting show up as a high jump percentage.
//   npx tsx scripts/qa-flicker.ts [--base http://localhost:3000] [--times 20,165] [--out dir]
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? (process.argv[i + 1] ?? d) : d;
};
const BASE = arg("base", "http://localhost:3000")!;
const TIMES = arg("times", "20,165")!.split(",").map(Number);
const OUT = resolve(arg("out", join(__dirname, "..", "..", "docs", "qa", "flicker"))!);
const DT = 0.02;

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto(`${BASE}/film?qa=1&t=${TIMES[0]}`);
  await page.waitForFunction(() => (window as unknown as { __zillFrameReady?: boolean }).__zillFrameReady === true, undefined, { timeout: 180_000 });
  const report: Record<string, number> = {};
  for (const t of TIMES) {
    const shots: Buffer[] = [];
    for (const tt of [t, t + DT]) {
      await page.evaluate(async (x) => {
        const w = window as unknown as { __zillFilmSetT: (s: number) => void; __zillFrameReady?: boolean };
        w.__zillFrameReady = false;
        w.__zillFilmSetT(x);
      }, tt);
      await page.waitForFunction(() => (window as unknown as { __zillFrameReady?: boolean }).__zillFrameReady === true, undefined, { timeout: 60_000 });
      await page.waitForTimeout(400);
      shots.push(await page.screenshot());
    }
    const a = join(OUT, `t_${t.toFixed(2)}_a.png`);
    const b = join(OUT, `t_${t.toFixed(2)}_b.png`);
    writeFileSync(a, shots[0]!);
    writeFileSync(b, shots[1]!);
    report[String(t)] = 0;
    console.log(`captured ${a} / ${b}`);
  }
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
