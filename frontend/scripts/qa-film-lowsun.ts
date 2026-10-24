// Low-sun grade check (Stream G): /app stills of Oslo at a midwinter noon (pale, cool daylight) and
// Dubai at golden hour (unchanged warm), to verify the generic low-sun day grade in three/lighting.
//   npx tsx scripts/qa-film-lowsun.ts --base http://localhost:3011 --out ../docs/qa/overnight-film/lowsun
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "@playwright/test";

const arg = (k: string, d: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? (process.argv[i + 1] ?? d) : d;
};
const BASE = arg("base", "http://localhost:3000");
const OUT = resolve(arg("out", join(__dirname, "..", "..", "docs", "qa", "overnight-film", "lowsun")));
const SHOTS = [
  { name: "oslo_winter_1200", q: "city=oslo&date=winter&time=1200" },
  { name: "oslo_winter_1000", q: "city=oslo&date=winter&time=1000" },
  { name: "dubai_hackathon_1720", q: "date=hackathon&time=1720" },
  { name: "dubai_winter_1230", q: "date=winter&time=1230" },
];

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  for (const s of SHOTS) {
    await page.goto(`${BASE}/app?${s.q}`, { waitUntil: "domcontentloaded", timeout: 180_000 });
    await page.waitForTimeout(9000);
    await page.screenshot({ path: join(OUT, `${s.name}.png`) });
    console.log(s.name);
  }
  await browser.close();
}
void main();
