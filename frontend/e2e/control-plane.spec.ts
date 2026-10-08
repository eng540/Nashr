import { expect, test } from "@playwright/test";

test("control plane lists the editorial prompt", async ({ page }) => {
  await page.goto("/control");
  await expect(page.getByText("التعليمات التحريرية")).toBeVisible();
  await expect(page.getByText("E2E Control Prompt")).toBeVisible();
});
