// Backup film recorder (PRD 17.6): Playwright video of the autoplaying Film at 1920x1080.
//   npx tsx scripts/record-film.ts [--out ../docs/deck_assets/backup_film] [--rate 1] [--seconds 780]
//                                  [--swiftshader] [--base http://localhost:3000] [--no-mp4] [--crf 20]
// Realtime (rate 1) takes ~13 min: run it in the background. `--rate N` uses the film's `?rate=N`
// QA speed-up (only for smoke-testing the recorder; a real backup must be realtime).
// Output: <out>.webm and <out>.mp4 (H.264, crf 20, yuv420p; ffmpeg from imageio-ffmpeg).
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import {
  BASE,
  DECK_DIR,
  arg,
  attachLogs,
  ensureServer,
  finishVideo,
  flag,
  launch,
  rendererName,
  sleep,
  toMp4,
  waitReady,
} from "./record-common";

const FILM_NOMINAL_S = 780; // PRD 14.2, sum of the chapter durations (src/film/master.ts)

async function main() {
  await ensureServer();
  const out = resolve(arg("out", join(DECK_DIR, "backup_film"))!);
  const rate = Number(arg("rate", "1"));
  // wall-clock cap: nominal film length / (rate * 0.85 min speed) as an upper bound; the loop ends earlier at film end
  const seconds = Number(arg("seconds", String(FILM_NOMINAL_S / rate / 0.85)));
  mkdirSync(join(out, ".."), { recursive: true });
  const tmp = mkdtempSync(join(tmpdir(), "zill-film-"));

  const { browser, gpu } = await launch(flag("swiftshader"));
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: tmp, size: { width: 1920, height: 1080 } },
  });
  const page = await ctx.newPage();
  const logs: string[] = [];
  attachLogs(page, logs);

  const url = `${BASE}/film?qa=1${rate !== 1 ? `&rate=${rate}` : ""}`;
  console.log(`recording ${url} for ${seconds.toFixed(0)} s (gpu: ${gpu})`);
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 180_000 });
  const ready = await waitReady(page);
  if (!ready) logs.push("[timeout] __zillReady never became true; recording anyway");
  console.log(`renderer: ${await rendererName(page)}`);
  await sleep(1500);
  // Start autoplay from the top: Home/scroll top, then Space (PRD 14.1).
  await page.evaluate(() => {
    const w = window as unknown as { __zillFilmSetT?: (t: number) => void };
    if (w.__zillFilmSetT) w.__zillFilmSetT(0);
    else window.scrollTo(0, 0);
  });
  await sleep(1500);
  await page.keyboard.press("Space");
  const t0 = Date.now();
  let lastLog = 0;
  // Stop when the film reports its end (window.__zillFilm.t from FilmWorld) or after the time cap.
  while ((Date.now() - t0) / 1000 < seconds + 6) {
    await sleep(2000);
    const el = (Date.now() - t0) / 1000;
    const ft = await page.evaluate(() => (window as unknown as { __zillFilm?: { t: number } }).__zillFilm?.t ?? -1);
    if (ft >= FILM_NOMINAL_S - 0.5 && !flag("full-cap")) {
      console.log(`  film reached ${ft.toFixed(1)} s; holding the last frame for 4 s`);
      await sleep(4000);
      break;
    }
    if (el - lastLog >= 60) {
      lastLog = el;
      console.log(`  ... ${el.toFixed(0)} s wall / film t = ${ft.toFixed(1)} s`);
    }
  }
  await page.keyboard.press("Escape");

  await finishVideo(ctx, page, tmp, `${out}.webm`);
  await browser.close();
  if (!flag("no-mp4")) toMp4(`${out}.webm`, `${out}.mp4`);
  if (logs.length) console.warn(`console errors (${logs.length}):\n` + logs.slice(0, 20).join("\n"));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
