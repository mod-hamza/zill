// Deck-asset exporter (PRD 17.4, 19.3): 1920x1080 stills of the Film at the best moment of each chapter.
//   npx tsx scripts/export-deck-assets.ts [--out ../docs/deck_assets/stills] [--public ../frontend/public/stills]
//                                         [--only 06,07] [--swiftshader] [--q high] [--base http://localhost:3000]
// Chapters/durations: read from `window.__zillChapters` (exposed by src/film/master.ts) when the page
// has it, otherwise the PRD 14.2 table below. Seeking uses the Film's QA hook `/film?qa=1&t=<seconds>`
// and waits for `window.__zillFrameReady`. Stills are named NN_<chapter-slug>.png; the same files are
// copied to frontend/public/stills/ (WebGL-failure fallback) with a manifest.json.
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { Page } from "@playwright/test";
import {
  BASE,
  DECK_DIR,
  ROOT,
  arg,
  attachLogs,
  ensureServer,
  flag,
  launch,
  rendererName,
  sleep,
  waitReady,
} from "./record-common";

type Chapter = { id: number; slug: string; title: string; dur_s: number };

const slugify = (t: string): string =>
  t
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

// PRD 14.2 (fallback when the page does not expose its chapters). Sum = 780 s.
const PRD_CHAPTERS: Chapter[] = [
  { id: 1, slug: "dubai-1300", title: "Dubai, 13:00.", dur_s: 40 },
  { id: 2, slug: "the-problem", title: "The problem.", dur_s: 50 },
  { id: 3, slug: "shade-moves", title: "Shade moves.", dur_s: 55 },
  { id: 4, slug: "a-city-built", title: "A city, built in seconds.", dur_s: 90 },
  { id: 5, slug: "the-shade-engine", title: "The shade engine.", dur_s: 90 },
  { id: 6, slug: "the-route", title: "The route.", dur_s: 150 },
  { id: 7, slug: "leave-later", title: "Leave later.", dur_s: 70 },
  { id: 8, slug: "an-agent-not-a-map", title: "An agent, not a map.", dur_s: 60 },
  { id: 9, slug: "who-its-for", title: "Who it's for.", dur_s: 60 },
  { id: 10, slug: "does-it-work", title: "Does it work?", dur_s: 40 },
  { id: 11, slug: "any-hot-city", title: "Any hot city.", dur_s: 40 },
  { id: 12, slug: "the-ask", title: "The ask.", dur_s: 35 },
];

// Best chapter-local t per still (what is on screen there, per PRD 14.2). 14 stills; chapter 6 gets three.
type Plan = { ch: number; t: number; suffix?: string };
const PLAN: Plan[] = [
  { ch: 1, t: 0.82 }, // title + one-liner over the lit skyline
  { ch: 2, t: 0.72 }, // street level, ember sun-exposure HUD high
  { ch: 3, t: 0.93 }, // hold at 16:00, tower shadows over whole streets
  { ch: 4, t: 0.83 }, // 74.7 s: counters final (ramp 62-72 s) and still visible (fade-out from ~76.5 s), ch04.ts
  { ch: 5, t: 0.62 }, // per-edge exposure labels + schematic
  { ch: 6, t: 0.22, suffix: "feed" }, // agent activity feed, two routes
  { ch: 6, t: 0.5, suffix: "flythrough" }, // fly-through with HUD
  { ch: 6, t: 0.94, suffix: "compare" }, // split view / comparison card
  { ch: 7, t: 0.75 }, // departure chart + recommendation
  { ch: 8, t: 0.7 }, // proactive replan diff
  { ch: 9, t: 0.82 }, // revenue table
  { ch: 10, t: 0.6 }, // evidence / field-test plan
  { ch: 11, t: 0.75 }, // globe + roadmap
  { ch: 12, t: 0.7 }, // golden hour, closing line
];

const pad = (n: number) => String(n).padStart(2, "0");

/** Chapter list: the page's window.__zillChapters if exposed, else parse CHAPTERS from src/film/master.ts
 *  (the single source of truth), else the PRD 14.2 table. */
async function readChapters(page: Page): Promise<{ chapters: Chapter[]; source: string }> {
  const live = await page.evaluate(() => {
    const w = window as unknown as { __zillChapters?: { title?: string; dur_s?: number }[] };
    return w.__zillChapters ?? null;
  });
  if (live && live.length > 0) {
    return {
      chapters: live.map((c, i) => ({
        id: i + 1,
        title: c.title ?? `Chapter ${i + 1}`,
        slug: slugify(c.title ?? `chapter-${i + 1}`),
        dur_s: Number(c.dur_s ?? 0),
      })),
      source: "window.__zillChapters",
    };
  }
  const master = join(ROOT, "frontend", "src", "film", "master.ts");
  if (existsSync(master)) {
    const text = readFileSync(master, "utf-8");
    const re = /id:\s*"ch(\d+)",\s*title:\s*"((?:[^"\\]|\\.)*)",\s*dur_s:\s*(\d+)/g;
    const found: Chapter[] = [];
    for (let m = re.exec(text); m; m = re.exec(text)) {
      const title = JSON.parse(`"${m[2]}"`) as string;
      found.push({ id: Number(m[1]), title, slug: slugify(title), dur_s: Number(m[3]) });
    }
    if (found.length === PRD_CHAPTERS.length) return { chapters: found, source: "src/film/master.ts CHAPTERS" };
  }
  return { chapters: PRD_CHAPTERS, source: "PRD 14.2 table (CHAPTERS not readable)" };
}

async function main() {
  await ensureServer();
  const outDir = resolve(arg("out", join(DECK_DIR, "stills"))!);
  const pubDir = resolve(arg("public", join(ROOT, "frontend", "public", "stills"))!);
  const only = arg("only")?.split(",");
  const q = arg("q", "high")!;
  mkdirSync(outDir, { recursive: true });
  mkdirSync(pubDir, { recursive: true });

  const { browser, gpu } = await launch(flag("swiftshader"));
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const logs: string[] = [];
  attachLogs(page, logs);

  await page.goto(`${BASE}/film?qa=1&q=${q}&t=0`, { waitUntil: "domcontentloaded", timeout: 180_000 });
  if (!(await waitReady(page))) logs.push("[timeout] first load never became ready");
  const { chapters, source } = await readChapters(page);
  console.log(`chapters from ${source}; gpu ${gpu}; renderer ${await rendererName(page)}`);

  const starts: number[] = [];
  let acc = 0;
  for (const c of chapters) {
    starts.push(acc);
    acc += c.dur_s;
  }

  const manifest: { file: string; chapter: number; title: string; global_t_s: number; chapter_t: number }[] = [];
  for (const p of PLAN) {
    const c = chapters[p.ch - 1]!;
    const num = pad(p.ch);
    if (only && !only.includes(num)) continue;
    const gt = starts[p.ch - 1]! + p.t * c.dur_s;
    const name = `${num}_${c.slug}${p.suffix ? `-${p.suffix}` : ""}.png`;
    const hasSeek = await page.evaluate(
      () => typeof (window as unknown as { __zillFilmSetT?: unknown }).__zillFilmSetT === "function",
    );
    let ready = true;
    if (hasSeek) {
      await page.evaluate((x) => (window as unknown as { __zillFilmSetT: (t: number) => void }).__zillFilmSetT(x), gt);
      await sleep(400);
    } else {
      await page.goto(`${BASE}/film?qa=1&q=${q}&t=${gt.toFixed(2)}`, { waitUntil: "domcontentloaded", timeout: 180_000 });
      ready = await waitReady(page, 120_000);
    }
    try {
      await page.waitForFunction(
        () => (window as unknown as { __zillFrameReady?: boolean }).__zillFrameReady === true,
        undefined,
        { timeout: 90_000, polling: 250 },
      );
    } catch {
      logs.push(`[timeout] ${name} frame never ready`);
    }
    await sleep(2500);
    const file = join(outDir, name);
    await page.screenshot({ path: file });
    copyFileSync(file, join(pubDir, name));
    manifest.push({ file: name, chapter: p.ch, title: c.title, global_t_s: Number(gt.toFixed(2)), chapter_t: p.t });
    console.log(`${name}  global t ${gt.toFixed(1)} s${ready ? "" : "  (NOT READY)"}`);
  }
  writeFileSync(
    join(pubDir, "manifest.json"),
    JSON.stringify({ generated: new Date().toISOString(), chapters_source: source, gpu, stills: manifest }, null, 2),
  );
  copyFileSync(join(pubDir, "manifest.json"), join(outDir, "manifest.json"));
  await browser.close();
  if (logs.length) console.warn(`warnings (${logs.length}):\n` + logs.slice(0, 20).join("\n"));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
