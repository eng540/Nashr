import { test, expect } from "@playwright/test";

test("publishing selection follows 0 -> 1 -> 0 contract", async ({ page }) => {
  await page.goto("/publishing");
  const createPlan = page.getByTestId("create-plan");
  await expect(createPlan).toBeDisabled();

  const checkbox = page.getByRole("checkbox").first();
  await expect(checkbox).toBeVisible();
  await checkbox.check();
  await expect(createPlan).toBeEnabled();

  await checkbox.uncheck();
  await expect(createPlan).toBeDisabled();
});
