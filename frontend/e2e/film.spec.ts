import { expect, test, type Page } from "@playwright/test";

// Film smoke (PRD 18.2): loads, Space advances, chapter jump works, a sped-up full autoplay
// (?qa=1&rate=…) reaches the end with no console errors.
const errors: string[] = [];

function watch(page: Page) {
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
}

const filmT = (page: Page) =>
  page.evaluate(() => (window as unknown as { __zillFilm?: { t: number; chapter: number } }).__zillFilm ?? null);

test.describe("film", () => {
  test.setTimeout(300_000);

  test("loads, Space plays, arrow jumps a chapter", async ({ page }) => {
    watch(page);
    await page.goto("/film");
    await expect(page.getByRole("heading", { name: "Zill" })).toBeAttached();
    await page.waitForFunction(() => (window as unknown as { __zillFilm?: unknown }).__zillFilm, undefined, { timeout: 120_000 });
    await page.keyboard.press("Space");
    // software GL is slow: wait for the clock to move rather than a fixed amount
    await page.waitForFunction(() => ((window as unknown as { __zillFilm?: { t: number } }).__zillFilm?.t ?? 0) > 0.05, undefined, { timeout: 60_000 });
    const a = await filmT(page);
    expect(a!.t).toBeGreaterThan(0.05);
    await page.keyboard.press("Escape");
    await page.keyboard.press("4");
    await page.waitForFunction(() => (window as unknown as { __zillFilm?: { chapter: number } }).__zillFilm?.chapter === 4, undefined, { timeout: 60_000 });
    await page.waitForTimeout(3000); // let the 1.2 s eased jump finish
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(() => (window as unknown as { __zillFilm?: { chapter: number } }).__zillFilm?.chapter === 5, undefined, { timeout: 60_000 });
  });

  test("fast autoplay reaches 13:00 without console errors", async ({ page }) => {
    errors.length = 0;
    watch(page);
    await page.goto("/film?qa=1&t=0&rate=40&autoplay=1&q=low");
    await page.waitForFunction(
      () => ((window as unknown as { __zillFilm?: { t: number } }).__zillFilm?.t ?? 0) >= 779.9,
      undefined,
      { timeout: 280_000, polling: 1000 },
    );
    const real = errors.filter((e) => !/favicon|preload|Download the React DevTools/i.test(e));
    expect(real).toEqual([]);
  });
});
