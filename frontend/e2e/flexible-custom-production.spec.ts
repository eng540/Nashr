import { test, expect } from "@playwright/test";

test("custom production submits direct text and instructions without a product", async ({ page }) => {
  let submittedPayload: Record<string, unknown> | null = null;

  await page.route("**/api/control/products", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{ id: "post-recipe-id", key: "BOOK_TO_TELEGRAM_POST", name: "Book to Telegram Post", purpose: "Post production", active_version: 1, versions: [{ version: 1, status: "PUBLISHED", stages: [{ key: "produce-post", capability_key: "produce_post", capability_version: 1 }] }] }] }));
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
  await page.getByLabel("مسار الإنتاج النصي").selectOption("BOOK_TO_TELEGRAM_POST");
  await page.getByLabel("النص المدخل").fill("هذا نص مباشر للاختبار.");
  await page.getByLabel("التوجيه المخصص").fill("اشرح الفرق الدلالي");
  await page.getByTestId("start-custom-production").click();

  await expect.poll(() => submittedPayload).not.toBeNull();
  expect(submittedPayload).toMatchObject({
    scope: "SELECTION",
    production_mode: "CUSTOM",
    input_text: "هذا نص مباشر للاختبار.",
    custom_instructions: "اشرح الفرق الدلالي",
    recipe_key: "BOOK_TO_TELEGRAM_POST"
  });
  expect(submittedPayload).not.toHaveProperty("product_key");
});



test("product mode can use direct text and task-specific instructions without a library source", async ({ page }) => {
  const productKey = "E2E_POST_PRODUCT";
  const identityKey = "E2E_POST_IDENTITY";
  const recipeKey = "E2E_POST_RECIPE";
  let submittedPayload: Record<string, unknown> | null = null;
  const manifest = {
    prompt: { key: "editorial.drafter", version_id: "10000000-0000-4000-8000-000000000001", version: 1 },
    identity: { key: identityKey, version_id: "10000000-0000-4000-8000-000000000002", version: 1 },
    recipe: { key: recipeKey, version_id: "10000000-0000-4000-8000-000000000003", version: 1 },
    policy: { key: "EDITORIAL_DEFAULT", version_id: "10000000-0000-4000-8000-000000000004", version: 1 },
    output_contract: { key: "TELEGRAM_POST", version_id: "10000000-0000-4000-8000-000000000005", version: 1 },
  };

  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [{
    id: "identity-id", key: identityKey, name: "E2E Identity", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED" }]
  }] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{
    id: "recipe-id", key: recipeKey, name: "E2E Post Recipe", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", stages: [{ key: "produce", capability_key: "produce_post", capability_version: 1 }] }]
  }] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [{
    id: "product-id", key: productKey, name: "E2E Product", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", definition: {
      recipe_key: recipeKey, output_contract_key: "TELEGRAM_POST", policy_key: "EDITORIAL_DEFAULT",
      prompt_key: "editorial.drafter", identity_key: identityKey, component_versions: manifest,
      audience: "readers", experience: "post"
    } }]
  }] }));
  await page.route("**/sources**", (route) => route.fulfill({ json: [] }));
  await page.route("**/production-jobs/product-text-job", (route) => route.fulfill({ json: {
    job_id: "product-text-job", source_id: "inline-source", status: "COMPLETED", scope: "SELECTION",
    total_items: 1, completed_items: 1, failed_items: 0, pending_items: 0, running_items: 0,
    reconciliation_required_items: 0, current_item_id: null, attempts: 1, error_code: null, error_message: null,
    created_at: "", updated_at: "", started_at: "", completed_at: "", progress_percent: 100, next_action: "REVIEW_DRAFTS",
    resolved_prompt: { key: "editorial.drafter", version: 1, body: "pinned prompt", available: true },
    resolved_context: { available: true, invalid: false, schema_version: 6, origin: "RUNTIME_RESOLUTION", captured_at: "", prompt_template: null }
  } }));
  await page.route("**/production-jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submittedPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({
      job_id: "product-text-job", source_id: "inline-source", status: "QUEUED", scope: "SELECTION",
      total_items: 1, completed_items: 0, failed_items: 0, pending_items: 1, running_items: 0,
      reconciliation_required_items: 0, progress_percent: 0, next_action: "WAIT",
      resolved_prompt: { key: "editorial.drafter", version: 1, body: "pinned prompt", available: true },
      resolved_context: { available: true, invalid: false, schema_version: 6, origin: "RUNTIME_RESOLUTION", captured_at: "", prompt_template: null }
    }) });
  });

  await page.goto("/posts/workspace");
  await page.getByRole("button", { name: "منتج مع تعليمات إضافية" }).click();
  await page.getByLabel("المنتج").selectOption(productKey);
  await expect(page.getByLabel("الهوية التحريرية للإنتاج")).toHaveValue(identityKey);
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await page.getByRole("button", { name: "لصق نص مباشر" }).click();
  await page.getByLabel("النص المدخل").fill("نص مباشر داخل مسار المنتج.");
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await page.getByLabel("تعليمات إضافية لهذه المهمة").fill("اجعل النص موجزًا مع الحفاظ على دقة المعنى.");
  await page.getByTestId("start-production").click();

  await expect.poll(() => submittedPayload).not.toBeNull();
  expect(submittedPayload).toMatchObject({
    production_mode: "PRODUCT_WITH_INSTRUCTIONS",
    product_key: productKey,
    input_text: "نص مباشر داخل مسار المنتج.",
    custom_instructions: "اجعل النص موجزًا مع الحفاظ على دقة المعنى."
  });
  expect(submittedPayload).not.toHaveProperty("source_id");
});
