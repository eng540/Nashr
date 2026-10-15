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

test("generic text artifact review shows a live reader preview that preserves paragraphs", async ({ page }) => {
  const artifactId = "e2e-text-artifact";
  const original = "المطلع الأول.\\n\\nفقرة ثانية تتنفس بمسافة واضحة.\\nسطر ثانٍ داخل الفقرة.";
  await page.route("**/api/artifacts*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname !== "/api/artifacts" || url.searchParams.get("review_status") !== "DRAFT") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        id: artifactId,
        source_knowledge_unit_id: "e2e-source-material",
        kind: "TEXT",
        status: "AVAILABLE",
        content: original,
        storage_uri: null,
        mime_type: "text/plain",
        output_contract_key: "E2E_TEXT",
        output_contract_version: 1,
        metadata: { title: "معاينة نصية" },
        review_status: "DRAFT",
        review_note: null,
        reviewed_at: null,
        created_at: "2026-10-15T00:00:00Z",
        updated_at: "2026-10-15T00:00:00Z",
      }]),
    });
  });

  await page.goto("/posts/workspace?status=DRAFT");
  const preview = page.getByTestId(`artifact-text-preview-${artifactId}`);
  await expect(preview).toBeVisible();
  await expect(preview).toHaveText(original);

  const edited = "عنوان قصير\\n\\nنص محرر بفقرة مستقلة.";
  await page.getByLabel(`محتوى المخرج ${artifactId}`).fill(edited);
  await expect(preview).toHaveText(edited);
  await expect(preview).toHaveAttribute("dir", "auto");
});
