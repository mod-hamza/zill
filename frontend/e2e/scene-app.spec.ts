import { expect, test } from "@playwright/test";

// /app smoke (PRD 18.2): the city loads, a hero journey is requested from /api/route and the
// Journey panel renders computed stats. Needs `next dev` (or start) + the backend running.
test("app loads and a hero route request renders stats", async ({ page }) => {
  test.setTimeout(180_000);
  const fixture = process.env.ZILL_E2E_FIXTURE === "1" ? "&fixture=1" : "";
  await page.goto(`/app?qa=1&q=low${fixture}`);
  await page.waitForFunction(() => window.__zillReady === true, undefined, {
    timeout: 150_000,
  });
  await expect(page.getByText("Journey", { exact: true })).toBeVisible();

  // load hero scenarios, take the first, and ask the live router for it
  const ok = await page.evaluate(async () => {
    const z = window.__zill as {
      useRoute: {
        getState: () => {
          loadScenarios: () => Promise<void>;
          scenarios: { id: string }[];
          applyScenario: (id: string) => void;
          request: () => Promise<void>;
          result: unknown;
          error: string | null;
        };
      };
    };
    const r = z.useRoute.getState();
    await r.loadScenarios();
    const first = z.useRoute.getState().scenarios[0];
    if (!first) return "no-scenarios";
    z.useRoute.getState().applyScenario(first.id);
    await z.useRoute.getState().request();
    const s = z.useRoute.getState();
    return s.error ? `error: ${s.error}` : s.result ? "ok" : "no-result";
  });
  expect(ok).toBe("ok");
  await expect(page.getByText("Coolest", { exact: true })).toBeVisible();
  await expect(page.getByText(/min sun/).first()).toBeVisible();
  await expect(page.getByText(/shade$/).first()).toBeVisible();
});
