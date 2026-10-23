// Render an SVG file to PNG with Chromium (used for docs/deck_assets/architecture.png).
//   npx tsx scripts/render-svg.ts <in.svg> <out.png> [--scale 1]
// The viewport is taken from the SVG's width/height attributes (fallback 1920x1080).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "@playwright/test";

async function main() {
  const [inp, out] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
  if (!inp || !out) {
    console.error("usage: render-svg.ts <in.svg> <out.png> [--scale N]");
    process.exit(2);
  }
  const si = process.argv.indexOf("--scale");
  const scale = si >= 0 ? Number(process.argv[si + 1]) : 1;
  const text = readFileSync(inp, "utf-8");
  const w = Number(/<svg[^>]*\swidth="(\d+)/.exec(text)?.[1] ?? 1920);
  const h = Number(/<svg[^>]*\sheight="(\d+)/.exec(text)?.[1] ?? 1080);
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: scale });
  const page = await ctx.newPage();
  await page.goto(pathToFileURL(resolve(inp)).href);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: resolve(out), omitBackground: false });
  await browser.close();
  console.log(`rendered ${out} (${w}x${h} @${scale}x)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
