import { expect, test } from "@playwright/test";

const sourceA = "81111111-1111-4111-8111-111111111111";
const sourceB = "82222222-2222-4222-8222-222222222222";
const unitA = "83333333-3333-4333-8333-333333333333";
const unitB = "84444444-4444-4444-8444-444444444444";
const productKey = "ARABIC_LITERATURE_THEMATIC_TEXT";
const identityKey = "ARABIC_LITERATURE_BASELINE_V1";
const recipeKey = "BOOK_TO_THEMATIC_TEXT_ARTIFACT";
let submitted: Record<string, unknown> | null = null;

test("thematic product selects source materials across books and submits one ordered composition job", async ({ page }) => {
  submitted = null;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => { window.localStorage.clear(); });
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [{
    id: "identity-id", key: identityKey, name: "الهوية الأدبية الأمينة للمصدر", purpose: "test",
    active_version: 1, versions: [{ version: 1, status: "PUBLISHED" }],
  }] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{
    id: "recipe-id", key: recipeKey, name: "تركيب موضوعي متعدد المصادر", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", stages: [{
      key: "compose-thematic-text", capability_key: "compose_thematic_artifact", capability_version: 1,
    }] }],
  }] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [{
    id: "product-id", key: productKey, name: "النص الموضوعي متعدد المصادر", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", definition: {
      recipe_key: recipeKey, output_contract_key: "TEXT_ARTIFACT", policy_key: "EDITORIAL_DEFAULT",
      prompt_key: "editorial.drafter", identity_key: identityKey,
      component_versions: {
        prompt: { key: "editorial.drafter", version_id: "85555555-5555-4555-8555-555555555555", version: 1 },
        identity: { key: identityKey, version_id: "86666666-6666-4666-8666-666666666666", version: 1 },
        recipe: { key: recipeKey, version_id: "87777777-7777-4777-8777-777777777777", version: 1 },
        policy: { key: "EDITORIAL_DEFAULT", version_id: "88888888-8888-4888-8888-888888888888", version: 1 },
        output_contract: { key: "TEXT_ARTIFACT", version_id: "89999999-9999-4999-8999-999999999999", version: 1 },
      },
      audience: "قراء الأدب العربي", experience: "نص موضوعي قابل للمراجعة مع إحالات المصادر",
    } }],
  }] }));
  await page.route("**/sources**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/book-map")) {
      const isA = url.pathname.includes(sourceA);
      const sourceId = isA ? sourceA : sourceB;
      const unitId = isA ? unitA : unitB;
      const title = isA ? "مادة من الكتاب أ" : "مادة من الكتاب ب";
      const bookTitle = isA ? "الكتاب أ" : "الكتاب ب";
      const material = {
        id: unitId, position: 1, title, kind: "نص تراثي", content: isA ? "النص الأصلي أ" : "النص الأصلي ب",
        has_post: false, topic_id: null, source_reference: isA ? "ص 12" : "ص 41",
      };
      return route.fulfill({ json: {
        source_id: sourceId, book: { title: bookTitle, description: "" }, count: 1,
        topics: [], materials: [material],
      } });
    }
    return route.fulfill({ json: [
      { id: sourceA, filename: "book-a.pdf", book_title: "الكتاب أ", status: "READY", material_count: 1, produced_count: 0, pending_count: 1 },
      { id: sourceB, filename: "book-b.pdf", book_title: "الكتاب ب", status: "READY", material_count: 1, produced_count: 0, pending_count: 1 },
    ] });
  });
  await page.route("**/production-jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, json: {
      job_id: "thematic-job", source_id: sourceA, status: "QUEUED", scope: "SELECTION",
      total_items: 1, completed_items: 0, failed_items: 0, pending_items: 1, running_items: 0,
      reconciliation_required_items: 0, current_item_id: null, error_code: null, error_message: null,
      attempts: 0, created_at: "", updated_at: "", started_at: null, completed_at: null,
      progress_percent: 0, next_action: "WAIT",
      resolved_prompt: { key: "editorial.drafter", version: 1, body: null, available: false },
      resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
    } });
  });
  await page.route("**/production-jobs/thematic-job/items**", (route) => route.fulfill({
    json: { job_id: "thematic-job", total: 0, limit: 20, offset: 0, items: [] },
  }));
  await page.route("**/production-jobs/thematic-job", (route) => route.fulfill({ status: 200, json: {
    job_id: "thematic-job", source_id: sourceA, status: "QUEUED", scope: "SELECTION",
    total_items: 1, completed_items: 0, failed_items: 0, pending_items: 1, running_items: 0,
    reconciliation_required_items: 0, current_item_id: null, error_code: null, error_message: null,
    attempts: 0, created_at: "", updated_at: "", started_at: null, completed_at: null,
    progress_percent: 0, next_action: "WAIT",
    resolved_prompt: { key: "editorial.drafter", version: 1, body: null, available: false },
    resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
  } }));

  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toBeVisible();
  await expect(page.getByLabel("المنتج")).toHaveValue(productKey);
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await expect(page.getByLabel("الثيمة الموضوعية")).toBeVisible();
  await page.getByLabel("الثيمة الموضوعية").fill("الأمانة في نقل المعرفة بين كتب التراث");
  await expect(page.getByText("مادة من الكتاب أ", { exact: true })).toBeVisible();
  await expect(page.getByText("مادة من الكتاب ب", { exact: true })).toBeVisible();

  await page.getByText("مادة من الكتاب أ", { exact: true }).locator("xpath=ancestor::label").locator('input[type="checkbox"]').check();
  await page.getByText("مادة من الكتاب ب", { exact: true }).locator("xpath=ancestor::label").locator('input[type="checkbox"]').check();
  await expect(page.getByText("2 مادة محددة").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" })).toBeEnabled();
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toContainText("2 مادة من 2 كتاب");
  await page.getByTestId("start-production").click();
  await expect(page.getByTestId("production-job-details")).toBeVisible();

  expect(submitted).not.toBeNull();
  expect(submitted).toMatchObject({
    source_id: sourceA,
    scope: "SELECTION",
    product_key: productKey,
    thematic_theme: "الأمانة في نقل المعرفة بين كتب التراث",
    knowledge_unit_ids: [unitA, unitB],
  });
  expect(submitted?.idempotency_key).toBeTruthy();
});
