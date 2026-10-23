import { expect, test, type Page } from "@playwright/test";

// Agent panel end to end in replay mode (no LLM key): prompt chip -> streamed feed with tool rows
// and a verifier row -> final message with the truthful badge -> approval -> committed -> (replan
// recording) simulated delay -> replan diff card -> undo. Needs next dev/start + the backend.
async function openAgent(page: Page) {
  await page.goto("/app?qa=1&q=low&agent=1&agentSpeed=20");
  await page.waitForFunction(() => window.__zillReady === true, undefined, { timeout: 150_000 });
  await expect(page.getByTestId("agent-panel")).toBeVisible();
}

test("agent chat streams a recorded plan, then approval commits it", async ({ page }) => {
  test.setTimeout(240_000);
  await openAgent(page);
  const chip = page.getByTestId("chip-tourist_walk");
  await expect(chip).toBeVisible({ timeout: 30_000 });
  await chip.click();

  const feed = page.getByTestId("activity-feed").first();
  await expect(feed).toContainText("resolve place", { timeout: 30_000 });
  await expect(page.getByTestId("agent-message")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("agent-panel")).toContainText(/Verifier:\s+\d+ claims checked, \d+ supported/);
  const badge = page.getByTestId("feed-badge").first();
  await expect(badge).toHaveText(/Scripted session|Recorded session|Live/);

  await expect(page.getByTestId("agent-route-cards")).toBeVisible();
  const approval = page.getByTestId("agent-approval");
  await expect(approval).toBeVisible();
  await approval.getByRole("button", { name: /approve/i }).click();
  await expect(approval).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("agent-panel")).toContainText("Plan committed");
  // routes were set on the scene by the proposal
  const hasRoute = await page.evaluate(() => {
    const z = window.__zill as { useRoute: { getState: () => { result: unknown } } };
    return !!z.useRoute.getState().result;
  });
  expect(hasRoute).toBe(true);
});

test("simulated delay produces a replan card with undo", async ({ page }) => {
  test.setTimeout(240_000);
  await openAgent(page);
  const chip = page.getByTestId("chip-replan_demo");
  await expect(chip).toBeVisible({ timeout: 30_000 });
  await chip.click();
  const approval = page.getByTestId("agent-approval");
  await expect(approval).toBeVisible({ timeout: 60_000 });
  await approval.getByRole("button", { name: /approve/i }).click();
  const sim = page.getByTestId("sim-delay");
  await expect(sim).toBeEnabled({ timeout: 30_000 });
  await sim.click();
  const card = page.getByTestId("agent-replan");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText("Simulated event");
  await expect(card).toContainText(/Depart/);
  await page.getByTestId("agent-undo").click();
  await expect(card).toContainText("Reverted");
});
