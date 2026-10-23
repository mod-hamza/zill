/* eslint-disable @typescript-eslint/no-require-imports -- plain CommonJS node script */
// p95 frame time on the Film's heaviest chapters (PRD 18.4): real-time autoplay windows in ch4-6.
//   node scripts/perf-film.cjs [--base http://localhost:3000]
const { chromium } = require("@playwright/test");
const BASE = process.argv.includes("--base") ? process.argv[process.argv.indexOf("--base") + 1] : "http://localhost:3000";
const WINDOWS = [
  ["ch04", 185],
  ["ch05", 270],
  ["ch06_feed", 352],
  ["ch06_fly", 420],
  ["ch06_split", 455],
];
(async () => {
  const browser = await chromium.launch({ headless: true, args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--disable-gpu-vsync", "--disable-frame-rate-limit"] });
  const page = await (await browser.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
  const out = {};
  for (const [name, t] of WINDOWS) {
    await page.goto(`${BASE}/film?qa=1&debug=1&q=high&t=${t}`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => window.__zillFrameReady === true, undefined, { timeout: 180000 });
    await page.keyboard.press("Space");
    await page.waitForTimeout(6000);
    out[name] = await page.evaluate(() => window.__zillPerf);
    console.log(name, JSON.stringify(out[name]));
  }
  await browser.close();
  require("fs").writeFileSync(require("path").join(__dirname, "..", "..", "docs", "qa", "phase8", "perf.json"), JSON.stringify(out, null, 2));
})();
