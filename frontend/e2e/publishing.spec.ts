import { test, expect } from "@playwright/test";

test("approved post can be scheduled through the real API", async ({ page }) => {
  await page.goto("/publishing");
  await expect(page.getByTestId("publishing-workspace")).toBeVisible();

  const checkbox = page.getByRole("checkbox").first();
  await expect(checkbox).toBeVisible();
  await checkbox.check();
  await expect(page.getByTestId("create-plan")).toBeEnabled();

  await page.getByTestId("create-plan").click();
  await expect(page.getByTestId("schedule-panel")).toBeVisible();

  const scheduleResponse = page.waitForResponse((response) =>
    response.url().endsWith("/schedules") && response.request().method() === "POST",
  );

  await page.getByLabel("اسم الخطة").fill("E2E خطة نشر");
  await page.getByLabel("وقت البداية").fill("2030-01-01T12:00");
  await page.getByLabel("الفاصل بالدقائق").fill("60");
  await page.getByTestId("submit-schedule").click();

  const response = await scheduleResponse;
  expect(response.status()).toBe(201);
  const request = response.request().postDataJSON();
  expect(request.post_ids).toHaveLength(1);
  expect(request.name).toBe("E2E خطة نشر");
  await expect(page.getByRole("status")).toContainText("تم إنشاء الخطة بنجاح");
});
