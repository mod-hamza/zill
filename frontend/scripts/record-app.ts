// Backup /app demo recorder (PRD 17.6): ~90 s scripted walk-through at 1920x1080.
//   npx tsx scripts/record-app.ts [--out ../docs/deck_assets/backup_app_demo] [--swiftshader] [--no-mp4]
// Script: summer 13:30 -> hero chip -> routes (presentation, then analysis) -> fly-through ->
//         sun scrub 13:30 -> 16:00 -> agent (replan_demo replay) -> approve -> simulated delay -> replan.
// Every step is best-effort: a missing control is logged and skipped so the recording still completes.
// The agent runs in whatever mode the backend is in (live with a key, otherwise replay); the app's own
// badge ("Recorded session" / "Scripted session") shows which, so the video never pretends.
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import type { Page } from "@playwright/test";
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

const notes: string[] = [];

async function step(name: string, fn: () => Promise<void>): Promise<void> {
  const t = Date.now();
  try {
    await fn();
    console.log(`  ok   ${name} (${((Date.now() - t) / 1000).toFixed(1)} s)`);
  } catch (e) {
    const msg = String(e).split("\n")[0] ?? "error";
    notes.push(`${name}: ${msg}`);
    console.warn(`  skip ${name}: ${msg}`);
  }
}

async function scrubTime(page: Page, fromMin: number, toMin: number, ms: number): Promise<void> {
  const slider = page.getByLabel("Time of day");
  const n = 40;
  for (let i = 0; i <= n; i++) {
    const v = Math.round(fromMin + ((toMin - fromMin) * i) / n);
    await slider.fill(String(v), { timeout: 3000 });
    await sleep(ms / n);
  }
}

async function main() {
  await ensureServer();
  const out = resolve(arg("out", join(DECK_DIR, "backup_app_demo"))!);
  mkdirSync(join(out, ".."), { recursive: true });
  const tmp = mkdtempSync(join(tmpdir(), "zill-app-"));
  const { browser, gpu } = await launch(flag("swiftshader"));
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: tmp, size: { width: 1920, height: 1080 } },
  });
  const page = await ctx.newPage();
  const logs: string[] = [];
  attachLogs(page, logs);

  console.log(`recording /app demo (gpu: ${gpu})`);
  await page.goto(`${BASE}/app?date=summer&time=1330&q=high`, { waitUntil: "domcontentloaded", timeout: 180_000 });
  if (!(await waitReady(page))) notes.push("__zillReady timeout");
  console.log(`renderer: ${await rendererName(page)}`);
  await sleep(3000);

  await step("hero chip (Tourist walk)", async () => {
    await page.getByRole("button", { name: "Tourist walk" }).click({ timeout: 8000 });
    await sleep(7000);
  });
  await step("analysis view", async () => {
    await page.getByRole("button", { name: "Analysis" }).click({ timeout: 4000 });
    await sleep(4000);
    await page.getByRole("button", { name: "Presentation" }).click({ timeout: 4000 });
    await sleep(2500);
  });
  await step("fly-through", async () => {
    await page.getByRole("button", { name: "Fly me through it" }).click({ timeout: 4000 });
    await sleep(16_000);
    const stop = page.getByRole("button", { name: "Stop fly-through" });
    if (await stop.isVisible()) await stop.click();
    await sleep(1500);
  });
  await step("sun scrub 13:30 -> 16:00", async () => {
    await scrubTime(page, 13 * 60 + 30, 16 * 60, 9000);
    await sleep(1500);
  });
  await step("agent panel + recorded replan prompt", async () => {
    // replan_demo is the one recorded session that carries the approve -> simulated-delay phases.
    await page.getByRole("button", { name: "Agent", exact: true }).click({ timeout: 4000 });
    await sleep(1500);
    await page.getByTestId("chip-replan_demo").click({ timeout: 6000 });
    await page.getByTestId("agent-approval").waitFor({ timeout: 60_000 });
    await sleep(3000);
  });
  await step("approve plan", async () => {
    await page.getByTestId("agent-approval").getByRole("button", { name: /approve/i }).first().click({ timeout: 4000 });
    await sleep(3500);
  });
  await step("simulated 20 min delay", async () => {
    await page.getByTestId("sim-delay").click({ timeout: 30_000 }); // waits until enabled
    await page.getByTestId("agent-replan").waitFor({ timeout: 45_000 });
    await sleep(6000);
  });

  await finishVideo(ctx, page, tmp, `${out}.webm`);
  await browser.close();
  if (!flag("no-mp4")) toMp4(`${out}.webm`, `${out}.mp4`);
  if (notes.length) console.warn("skipped/failed steps:\n  " + notes.join("\n  "));
  if (logs.length) console.warn(`console errors (${logs.length}):\n` + logs.slice(0, 20).join("\n"));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
