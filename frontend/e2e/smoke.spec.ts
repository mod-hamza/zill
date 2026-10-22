import { expect, test } from "@playwright/test";

test("film landing shows the brand", async ({ page }) => {
  await page.goto("/film");
  await expect(page.getByRole("heading", { name: "Zill" })).toBeVisible();
  await expect(page.getByText("routes you through the shade")).toBeVisible();
});
