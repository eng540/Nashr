import { test, expect } from "@playwright/test";

test("Post Bank hands selection to Publishing through URL state only", async ({ page }) => {
  await page.goto("/posts/workspace?status=APPROVED");
  const checkbox = page.getByRole("checkbox").first();
  await expect(checkbox).toBeVisible();
  await checkbox.check();

  await page.getByTestId("go-publishing").click();
  await expect(page).toHaveURL(/\/publishing\?selected_post_ids=/);
  await expect(page.getByTestId("publishing-workspace")).toBeVisible();
  await expect(page.getByTestId("selection-count")).toContainText("1 محدد");
});
