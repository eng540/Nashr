import { expect, test } from "@playwright/test";

test("control plane keeps prompt management available beside product controls", async ({ page }) => {
  const response = await page.request.get("/api/control/prompts");
  expect(response.ok()).toBeTruthy();
  const prompts = await response.json();
  expect(prompts.some((prompt: { name: string }) => prompt.name === "E2E Control Prompt")).toBeTruthy();

  await page.goto("/control");
  await expect(page.getByRole("heading", { name: "التحكم في المنتجات والإنتاج" })).toBeVisible();
  await expect(page.getByRole("button", { name: "المنتجات" })).toBeVisible();
  await expect(page.getByRole("button", { name: "الوصفات" })).toBeVisible();
  await expect(page.getByRole("button", { name: "الهويات التحريرية" })).toBeVisible();
  await expect(page.getByRole("button", { name: "السياسات" })).toBeVisible();
  await expect(page.getByRole("button", { name: "عقود المخرجات" })).toBeVisible();

  await page.getByRole("button", { name: "التعليمات" }).click();
  await page.getByRole("button", { name: /E2E Control Prompt/ }).click();
  await expect(page.locator("textarea")).toHaveValue("E2E prompt body");
  await expect(page.getByText(/الإصدار المنشور:.*v1/)).toBeVisible();
});
