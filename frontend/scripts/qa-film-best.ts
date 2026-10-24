// Deck stills for the Zill & Shams film (Stream G): 1920x1080 JPEGs into docs/qa/best/, some "clean"
// (DOM overlays hidden: no baked-in UI text) and some with the panels.
//   npx tsx scripts/qa-film-best.ts --base http://localhost:3011
import { join, resolve } from "node:path";
import { chromium } from "@playwright/test";

const arg = (k: string, d: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? (process.argv[i + 1] ?? d) : d;
};
const BASE = arg("base", "http://localhost:3000");
const OUT = resolve(arg("out", join(__dirname, "..", "..", "docs", "qa", "best")));
const SHOTS: { name: string; t: number; clean: boolean }[] = [
  { name: "film_overnight_01_sunrise_clean", t: 33.5, clean: true },
  { name: "film_overnight_02_shade_moves_clean", t: 104, clean: true },
  { name: "film_overnight_03_two_directions_clean", t: 474, clean: true },
  { name: "film_overnight_04_oslo_long_shadows_clean", t: 494, clean: true },
  { name: "film_overnight_05_oslo_sunniest_clean", t: 512, clean: true },
  { name: "film_overnight_06_dusk_clean", t: 700, clean: true },
  { name: "film_overnight_07_two_directions_ui", t: 477.5, clean: false },
  { name: "film_overnight_08_oslo_ui", t: 533.5, clean: false },
  { name: "film_overnight_09_costs_ui", t: 725.5, clean: false },
  { name: "film_overnight_10_who_pays_ui", t: 639.5, clean: false },
];

async function main() {
  const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto(`${BASE}/film2?qa=1&t=${SHOTS[0]!.t}`, { waitUntil: "domcontentloaded", timeout: 180_000 });
  for (const s of SHOTS) {
    await page.evaluate((t) => (window as unknown as { __zillFilmSetT?: (x: number) => void }).__zillFilmSetT?.(t), s.t);
    await page.waitForTimeout(150);
    await page.waitForFunction(() => window.__zillFrameReady === true, undefined, { timeout: 120_000, polling: 100 });
    await page.waitForTimeout(700);
    await page.evaluate((clean) => {
      const o = document.querySelector<HTMLElement>(".film-overlay");
      if (o) o.style.visibility = clean ? "hidden" : "";
    }, s.clean);
    await page.screenshot({ path: join(OUT, `${s.name}.jpg`), type: "jpeg", quality: 88 });
    console.log(s.name);
  }
  await browser.close();
}
void main();
