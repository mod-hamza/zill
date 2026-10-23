// Render the deck to PDF + per-slide QA PNGs. Run from frontend/: node ../docs/pitch/deck/render.mjs [qaDir]
import { createRequire } from 'node:module';
const { chromium } = createRequire(process.cwd() + '/package.json')('playwright');
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const qa = process.argv[2];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(pathToFileURL(path.join(here, 'index.html')).href, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(500);
if (qa) {
  const n = await page.locator('section.slide').count();
  for (let i = 0; i < n; i++) {
    await page.locator('section.slide').nth(i).screenshot({ path: path.join(qa, `slide-${String(i + 1).padStart(2, '0')}.png`) });
  }
}
await page.emulateMedia({ media: 'print' });
await page.pdf({ path: path.join(here, '..', 'Zill-and-Shams-pitch.pdf'), width: '1920px', height: '1080px', printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
await browser.close();
console.log('done');
