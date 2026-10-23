// Visual QA for the overnight App (Stream F): Zill & Shams rename, Shade <-> Sun, well-being card,
// typed places, city switch, night state, 375 px mobile. Boots Chromium against a running
// `next dev` (+ API) and saves stills into docs/qa/overnight-app/<iter>/.
//   npx tsx scripts/qa-app-overnight.ts --base http://localhost:3010 --out ../docs/qa/overnight-app/iter1
//        [--only name,name] [--swiftshader]
// Waits for window.__zillReady, then an optional DOM condition (route cards, dropdown, ...).
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium, type Page } from "@playwright/test";

type Shot = {
  name: string;
  query: string;
  mobile?: boolean;
  /** text typed into the command bar after load (dropdown stays open for the still) */
  type?: string;
  /** CSS selector that must exist before the still */
  waitFor?: string;
  /** scroll the journey panel to its bottom (well-being card) */
  scrollPanel?: boolean;
  settleMs?: number;
  /** click a city in the switch before the still */
  city?: string;
  /** JS evaluated in the page after load (QA-only state, e.g. the busy notice) */
  evalJs?: string;
};

const arg = (k: string, d?: string) => {
  const i = process.argv.indexOf(`--${k}`);
  return i >= 0 ? (process.argv[i + 1] ?? d) : d;
};
const flag = (k: string) => process.argv.includes(`--${k}`);

const BASE = arg("base", "http://localhost:3010")!;
const OUT = resolve(
  arg("out", join(__dirname, "..", "..", "docs", "qa", "overnight-app", "iter1"))!,
);
const ONLY = arg("only")?.split(",");
const SWIFT = flag("swiftshader");
const OSLO = arg("oslo", "oslo")!;

const enc = encodeURIComponent;

export const SHOTS: Shot[] = [
  {
    name: "01_dubai_shade_hero",
    query: "route=hero&pref=shade",
    waitFor: "[data-testid=route-cards]",
  },
  {
    name: "02_dubai_sun_hero",
    query: "route=hero&pref=sun",
    waitFor: "[data-testid=route-cards]",
  },
  {
    name: "03_dubai_sun_wellbeing",
    query: "route=hero&pref=sun",
    waitFor: "[data-testid=wellbeing-card]",
    scrollPanel: true,
  },
  {
    name: "04_dubai_typed_journey",
    query: `date=winter&ask=${enc("from Burj Park to Boulevard Plaza at 12:30 sunny")}`,
    waitFor: "[data-testid=wellbeing-card]",
    settleMs: 3500,
  },
  {
    name: "05_dubai_typed_search_dropdown",
    query: "date=hackathon&time=1600",
    type: "souk al",
    waitFor: "#zill-command-list",
  },
  {
    name: "06_dubai_typed_journey_dropdown",
    query: "date=hackathon&time=1600",
    type: "from opera to burj khalifa at 5pm",
    waitFor: "#zill-command-list",
  },
  {
    name: "07_dubai_night",
    query: "date=hackathon&time=1915",
    waitFor: "[data-testid=night-note]",
  },
  {
    name: "08_oslo_shade",
    query: `city=${OSLO}&date=winter&time=1200&ask=${enc("from Oslo Central Station to Akershus Fortress")}`,
    waitFor: "[data-testid=route-cards]",
    settleMs: 4000,
  },
  {
    name: "09_oslo_sun",
    query: `city=${OSLO}&date=winter&time=1200&pref=sun&ask=${enc("from Oslo Central Station to Akershus Fortress sunny")}`,
    waitFor: "[data-testid=wellbeing-card]",
    settleMs: 4000,
  },
  {
    name: "14_oslo_ambiguous_picker",
    query: `city=${OSLO}&date=winter&time=1200&ask=${enc("from Oslo Central Station to Aker Brygge")}`,
    waitFor: "#zill-command-list",
  },
  {
    name: "10_oslo_overview",
    query: `city=${OSLO}&date=winter&time=1230`,
  },
  {
    name: "13_switch_dubai_to_oslo",
    query: "date=winter&time=1200",
    city: "Oslo",
    type: "aker",
    waitFor: "#zill-command-list",
  },
  {
    name: "15_busy_retry_notice",
    query: "route=hero&pref=sun",
    evalJs: "window.__zill.useBusy.getState().set(Date.now() + 4000)",
    waitFor: "[data-testid=busy-note]",
    settleMs: 400,
  },
  {
    name: "11_mobile_dubai_sun",
    query: "route=hero&pref=sun",
    mobile: true,
    waitFor: "[data-testid=route-cards]",
  },
  {
    name: "12_mobile_typed",
    query: "date=hackathon&time=1600",
    mobile: true,
    type: "dubai mall",
    waitFor: "#zill-command-list",
  },
];

async function settle(page: Page, shot: Shot, logs: string[]) {
  try {
    await page.waitForFunction(() => window.__zillReady === true, undefined, {
      timeout: 150_000,
      polling: 250,
    });
  } catch {
    logs.push(`[timeout] ${shot.name} never became ready`);
  }
  if (shot.city) {
    await page.locator("[data-testid=city-switch] button", { hasText: shot.city }).click();
    await page.waitForFunction(() => window.__zillReady !== true, undefined, { timeout: 10_000 }).catch(() => {});
    await page.waitForFunction(() => window.__zillReady === true, undefined, {
      timeout: 150_000,
      polling: 250,
    }).catch(() => logs.push(`[timeout] ${shot.name} city switch`));
  }
  if (shot.type) {
    const input = page.locator("[data-testid=command-bar] input");
    await input.click();
    await input.pressSequentially(shot.type, { delay: 25 });
  }
  if (shot.evalJs) await page.evaluate(shot.evalJs);
  if (shot.waitFor) {
    try {
      await page.waitForSelector(shot.waitFor, { timeout: 30_000 });
    } catch {
      logs.push(`[missing] ${shot.name}: ${shot.waitFor}`);
    }
  }
  if (shot.scrollPanel)
    await page.evaluate(() => {
      const el = document.querySelector("[data-testid=journey-panel]");
      const card = document.querySelector("[data-testid=wellbeing-card]");
      if (el && card)
        el.scrollTop = (card as HTMLElement).offsetTop - 120;
    });
  await page.waitForTimeout(shot.settleMs ?? 2500);
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const args = SWIFT
    ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    : ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"];
  const browser = await chromium.launch({ headless: true, args });
  const logs: string[] = [];
  const report: Record<string, unknown> = { base: BASE, shots: {} };
  for (const shot of SHOTS) {
    if (ONLY && !ONLY.some((o) => shot.name.includes(o))) continue;
    const ctx = await browser.newContext(
      shot.mobile
        ? {
            viewport: { width: 375, height: 812 },
            deviceScaleFactor: 2,
            isMobile: true,
            hasTouch: true,
          }
        : { viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 },
    );
    const page = await ctx.newPage();
    page.on("console", (m) => {
      if (m.type() === "error")
        logs.push(`[${shot.name}] ${m.text().slice(0, 300)}`);
    });
    page.on("pageerror", (e) => logs.push(`[${shot.name} pageerror] ${e.message}`));
    const url = `${BASE}/app?qa=1&q=${shot.mobile ? "medium" : "high"}&${shot.query}`;
    const t0 = Date.now();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 180_000 });
    await settle(page, shot, logs);
    const file = join(OUT, `${shot.name}.png`);
    await page.screenshot({ path: file });
    const text = await page.evaluate(
      () =>
        (document.querySelector("[data-testid=journey-panel]") as HTMLElement | null)
          ?.innerText ?? "",
    );
    (report.shots as Record<string, unknown>)[shot.name] = {
      url,
      ms: Date.now() - t0,
      panel: text.slice(0, 1500),
    };
    console.log(`${shot.name}: ${Date.now() - t0} ms`);
    await ctx.close();
  }
  report.logs = logs.slice(0, 200);
  writeFileSync(join(OUT, "capture_report.json"), JSON.stringify(report, null, 2));
  if (logs.length) console.log(logs.join("\n"));
  await browser.close();
}

void main();
