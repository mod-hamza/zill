// QA capture for the APP stream. Usage (from frontend/): node ../docs/qa/app/capture.mjs iterN
// Needs next dev on :3000 and the backend on :8000. Writes PNGs to docs/qa/app/<iter>/.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import path from "node:path";
const require = createRequire(path.resolve("package.json"));
const { chromium } = require("@playwright/test");

const iter = process.argv[2] ?? "iter1";
const out = path.resolve("..", "docs", "qa", "app", iter);
mkdirSync(out, { recursive: true });
const BASE = "http://localhost:3000";

const browser = await chromium.launch({
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
const shot = async (page, name) => {
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  console.log("saved", name);
};
const ready = (page) => page.waitForFunction(() => window.__zillReady === true, undefined, { timeout: 150000 });

async function agentFlow(replanDemo) {
  const page = await ctx.newPage();
  await page.goto(`${BASE}/app?qa=1&q=low&agent=1&agentSpeed=${replanDemo ? 3 : 1}`);
  await ready(page);
  await page.getByTestId(replanDemo ? "chip-replan_demo" : "chip-tourist_walk").waitFor({ timeout: 30000 });
  if (!replanDemo) await shot(page, "01_agent_open_chips");
  await page.getByTestId(replanDemo ? "chip-replan_demo" : "chip-tourist_walk").click();
  if (!replanDemo) {
    await page.waitForTimeout(5500);
    await shot(page, "02_agent_midstream");
  }
  await page.getByTestId("agent-approval").waitFor({ timeout: 90000 });
  await page.waitForTimeout(1200);
  await shot(page, replanDemo ? "04_agent_approval_replan_session" : "03_agent_approval");
  if (!replanDemo) {
    await page.getByTestId("agent-approval").getByRole("button", { name: /approve/i }).click();
    await page.getByText("Plan committed").first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(800);
    await shot(page, "03b_agent_committed");
  } else {
    await page.getByTestId("agent-approval").getByRole("button", { name: /approve/i }).click();
    await page.getByTestId("sim-delay").waitFor({ state: "visible" });
    await page.waitForFunction(() => !document.querySelector('[data-testid="sim-delay"]').disabled, undefined, { timeout: 30000 });
    await page.getByTestId("sim-delay").click();
    await page.getByTestId("agent-replan").waitFor({ timeout: 60000 });
    await page.waitForTimeout(1500);
    await shot(page, "05_agent_replan");
  }
  await page.close();
}

async function view(name, file, wait) {
  const page = await ctx.newPage();
  await page.goto(`${BASE}/app?qa=1&q=low&view=${name}`);
  await ready(page);
  await page.getByTestId("view-panel").waitFor({ timeout: 30000 });
  await wait?.(page);
  await page.waitForTimeout(1200);
  await shot(page, file);
  await page.close();
}

await agentFlow(false);
await agentFlow(true);
await view("planner", "06_planner", async (p) => {
  await p.getByTestId("plan-run").click();
  await p.getByTestId("plan-result").waitFor({ timeout: 60000 });
});
await view("fleet", "07_fleet", async (p) => {
  await p.waitForFunction(() => document.querySelectorAll('[data-testid="fleet-riders"] [data-testid="shade-strip"]').length >= 20, undefined, { timeout: 120000 });
});
await view("crew", "08_crew", async (p) => {
  await p.getByTestId("crew-run").click();
  await p.getByTestId("plan-result").waitFor({ timeout: 60000 });
});

const emb = await ctx.newPage();
await emb.goto(`${BASE}/embed/hotel?hotel=Address%20Downtown`);
await emb.getByTestId("hotel-attraction").first().waitFor({ timeout: 30000 });
await emb.waitForFunction(() => document.querySelectorAll('[data-testid="hotel-attraction"] .tabular').length >= 3, undefined, { timeout: 60000 }).catch(() => {});
await emb.waitForTimeout(800);
await shot(emb, "09_hotel_embed");
await emb.setViewportSize({ width: 390, height: 800 });
await shot(emb, "09b_hotel_embed_mobile");
const h = await ctx.newPage();
await h.goto(`${BASE}/health`);
await h.waitForTimeout(4500);
await shot(h, "10_health");
await browser.close();
