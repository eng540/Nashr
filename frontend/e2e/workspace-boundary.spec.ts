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


test("approved text Artifact can start a card job only through a published card recipe", async ({ page }) => {
  const artifactId = "e2e-approved-text-for-card";
  let submittedPayload: Record<string, unknown> | null = null;
  await page.route("**/api/control/products", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{
      id: "product-id",
      key: "E2E_CARD_PRODUCT",
      name: "منتج البطاقات التجريبي",
      purpose: "Test card derivative",
      active_version: 1,
      versions: [{
        version: 1,
        status: "PUBLISHED",
        definition: {
          recipe_key: "E2E_CARD_RECIPE",
          output_contract_key: "E2E_CARD_PNG",
          policy_key: "EDITORIAL_DEFAULT",
          audience: "Readers",
          experience: "Read an approved text as a card",
        },
      }],
    }]),
  }));
  await page.route("**/api/control/recipes", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{
      id: "recipe-id",
      key: "E2E_CARD_RECIPE",
      name: "E2E Card Recipe",
      purpose: "Deterministic card",
      active_version: 1,
      versions: [{
        version: 1,
        status: "PUBLISHED",
        stages: [{ key: "render", capability_key: "render_approved_text_card", capability_version: 1, configuration: { width: 1080 } }],
      }],
    }]),
  }));
  await page.route("**/api/artifacts?review_status=APPROVED", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([{
      id: artifactId,
      source_knowledge_unit_id: "e2e-source-material",
      kind: "TEXT",
      status: "AVAILABLE",
      content: "نص معتمد للبطاقة.",
      storage_uri: null,
      mime_type: "text/plain",
      output_contract_key: "E2E_TEXT",
      output_contract_version: 1,
      metadata: { title: "نص معتمد" },
      review_status: "APPROVED",
      review_note: null,
      reviewed_at: "2026-10-15T00:00:00Z",
      created_at: "2026-10-15T00:00:00Z",
      updated_at: "2026-10-15T00:00:00Z",
    }]),
  }));
  await page.route("**/api/production-jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submittedPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ job_id: "e2e-card-job", status: "QUEUED" }) });
  });

  await page.goto("/posts/workspace?status=DRAFT");
  await page.getByLabel("حالة مراجعة المخرجات").selectOption("APPROVED");
  await expect(page.getByLabel(`منتج البطاقة ${artifactId}`)).toBeVisible();
  await page.getByLabel(`منتج البطاقة ${artifactId}`).selectOption("E2E_CARD_PRODUCT");
  await page.getByRole("button", { name: "إنتاج البطاقة" }).click();
  await expect.poll(() => submittedPayload).not.toBeNull();
  expect(submittedPayload).toMatchObject({
    scope: "SELECTION",
    source_artifact_id: artifactId,
    product_key: "E2E_CARD_PRODUCT",
    recipe_key: "E2E_CARD_RECIPE",
  });
  expect(String(submittedPayload?.idempotency_key)).toContain(artifactId);
});
