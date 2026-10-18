import { test, expect } from "@playwright/test";

test("custom production submits direct text and instructions without a product", async ({ page }) => {
  let submittedPayload: Record<string, unknown> | null = null;

  await page.route("**/api/control/products", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [] }));
  await page.route("**/sources*", (route) => route.fulfill({ json: [] }));
  await page.route("**/production-jobs/custom-text-job", (route) => route.fulfill({ json: {
    job_id: "custom-text-job", claim_id: "custom-claim", source_id: "inline-source", status: "COMPLETED",
    scope: "SELECTION", total_items: 1, completed_items: 1, failed_items: 0, pending_items: 0,
    running_items: 0, reconciliation_required_items: 0, current_item_id: null, attempts: 1,
    error_code: null, error_message: null, created_at: "2026-10-18T00:00:00Z",
    updated_at: "2026-10-18T00:00:00Z", started_at: "2026-10-18T00:00:00Z",
    completed_at: "2026-10-18T00:00:00Z", progress_percent: 100, next_action: "REVIEW_DRAFTS",
    resolved_prompt: { key: "editorial.drafter", version: 1, body: "pinned prompt", available: true },
    resolved_context: { available: true, invalid: false, schema_version: 6, origin: "RUNTIME_RESOLUTION", captured_at: "2026-10-18T00:00:00Z", prompt_template: null },
    request_details: { production_mode: "CUSTOM", product_key: null, custom_instructions: "اشرح الفرق الدلالي", input_title: "نص تجريبي", input_text_preview: "هذا نص مباشر", source_id: "inline-source", knowledge_unit_ids: [] }
  } }));
  await page.route("**/production-jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submittedPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({
      job_id: "custom-text-job", status: "QUEUED", source_id: "inline-source", scope: "SELECTION",
      total_items: 1, completed_items: 0, failed_items: 0, pending_items: 1, running_items: 0,
      reconciliation_required_items: 0, progress_percent: 0, next_action: "WAIT",
      resolved_prompt: { key: "editorial.drafter", version: 1, body: "pinned prompt", available: true },
      resolved_context: { available: true, invalid: false, schema_version: 6, origin: "RUNTIME_RESOLUTION", captured_at: "2026-10-18T00:00:00Z", prompt_template: null }
    }) });
  });

  await page.goto("/posts/workspace");
  await page.getByRole("button", { name: "توجيه مخصص — دون منتج" }).click();
  await page.getByLabel("النص المدخل").fill("هذا نص مباشر للاختبار.");
  await page.getByLabel("التوجيه المخصص").fill("اشرح الفرق الدلالي");
  await page.getByTestId("start-custom-production").click();

  await expect.poll(() => submittedPayload).not.toBeNull();
  expect(submittedPayload).toMatchObject({
    scope: "SELECTION",
    production_mode: "CUSTOM",
    input_text: "هذا نص مباشر للاختبار.",
    custom_instructions: "اشرح الفرق الدلالي"
  });
  expect(submittedPayload).not.toHaveProperty("product_key");
});
