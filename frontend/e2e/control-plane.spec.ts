import { expect, test } from "@playwright/test";

test("control plane lists the editorial prompt", async ({ page }) => {
  const response = await page.request.get("/api/control/prompts");
  expect(response.ok()).toBeTruthy();
  const prompts = await response.json();
  expect(prompts.some((prompt: { name: string }) => prompt.name === "E2E Control Prompt")).toBeTruthy();

  await page.goto("/control");
  await expect(page.getByText("التعليمات التحريرية")).toBeVisible();
  await expect(page.getByText("E2E Control Prompt")).toBeVisible();
});
