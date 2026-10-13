import { expect, test, type Page } from "@playwright/test";

const sourceId = "61111111-1111-4111-8111-111111111111";
const topicId = "62222222-2222-4222-8222-222222222222";
const productKey = "E2E_VISUAL_PRODUCT";
const identityKey = "E2E_VISUAL_IDENTITY";
const materials = Array.from({ length: 25 }, (_, index) => ({
  id: `63333333-3333-4333-8333-${String(index + 1).padStart(12, "0")}`,
  position: index + 1,
  title: index === 0 ? "مادة تجريبية أولى" : `مادة تجريبية ${index + 1}`,
  kind: index % 2 ? "TEXT" : "HTML",
  content: "نص تجريبي",
  has_post: false,
  topic_id: index === 0 ? topicId : null,
}));

async function mockFactoryApi(page: Page, failSources = false) {
  await page.addInitScript(() => { window.localStorage.clear(); });
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [{
    id: "identity-id", key: identityKey, name: "وحدة تحريرية تجريبية", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED" }],
  }] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{
    id: "recipe-id", key: "E2E_VISUAL_RECIPE", name: "وصفة تجريبية", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", stages: [{ key: "produce", capability_key: "produce_post", capability_version: 1 }] }],
  }] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [{
    id: "product-id", key: productKey, name: "منتج تجريبي", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", definition: {
      recipe_key: "E2E_VISUAL_RECIPE", output_contract_key: "TELEGRAM_POST", policy_key: "EDITORIAL_DEFAULT",
      prompt_key: "editorial.drafter", identity_key: identityKey,
      component_versions: {
        prompt: { key: "editorial.drafter", version_id: "20000000-0000-4000-8000-000000000001", version: 1 },
        identity: { key: identityKey, version_id: "20000000-0000-4000-8000-000000000002", version: 1 },
        recipe: { key: "E2E_VISUAL_RECIPE", version_id: "20000000-0000-4000-8000-000000000003", version: 1 },
        policy: { key: "EDITORIAL_DEFAULT", version_id: "20000000-0000-4000-8000-000000000004", version: 1 },
        output_contract: { key: "TELEGRAM_POST", version_id: "20000000-0000-4000-8000-000000000005", version: 1 },
      },
      audience: "readers", experience: "post",
    } }],
  }] }));
  await page.route("**/sources**", (route) => {
    if (failSources) return route.fulfill({ status: 503, json: { detail: "visual test source failure" } });
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/book-map")) return route.fulfill({ json: {
      source_id: sourceId, book: { title: "كتاب تجريبي", description: "" }, count: materials.length, materials,
      topics: [{ id: topicId, position: 1, title: "محور تجريبي", description: "", materials: [materials[0]] }],
    } });
    return route.fulfill({ json: [{
      id: sourceId, filename: "visual-test.pdf", book_title: "كتاب تجريبي", status: "READY",
      material_count: materials.length, produced_count: 0, pending_count: materials.length,
    }] });
  });
  await page.route("**/production-jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as { scope: string };
    await route.fulfill({ status: 202, json: {
      job_id: "visual-job-id", source_id: sourceId, status: "QUEUED", scope: body.scope,
      total_items: 1, completed_items: 0, failed_items: 0, pending_items: 1, running_items: 0,
      reconciliation_required_items: 0, current_item_id: null, error_code: null, error_message: null,
      attempts: 0, created_at: "", updated_at: "", started_at: null, completed_at: null,
      progress_percent: 0, next_action: "WAIT",
      resolved_prompt: { key: null, version: null, body: null, available: false },
      resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
    } });
  });
  await page.route("**/production-jobs/visual-job-id/items**", (route) => route.fulfill({
    json: { job_id: "visual-job-id", total: 0, limit: 20, offset: 0, items: [] },
  }));
  await page.route("**/production-jobs/visual-job-id", (route) => route.fulfill({ status: 200, json: {
    job_id: "visual-job-id", source_id: sourceId, status: "QUEUED", scope: "SOURCE",
    total_items: 1, completed_items: 0, failed_items: 0, pending_items: 1, running_items: 0,
    reconciliation_required_items: 0, current_item_id: null, error_code: null, error_message: null,
    attempts: 0, created_at: "", updated_at: "", started_at: null, completed_at: null,
    progress_percent: 0, next_action: "WAIT",
    resolved_prompt: { key: null, version: null, body: null, available: false },
    resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
  } }));
}

async function expectNoHorizontalOverflow(page: Page, label: string) {
  const metrics = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    direction: getComputedStyle(document.documentElement).direction,
  }));
  expect(metrics.direction, `${label}: الصفحة يجب أن تكون RTL`).toBe("rtl");
  expect(metrics.document, `${label}: لا ينبغي أن يتجاوز المحتوى عرض الشاشة (${metrics.document}px مقابل ${metrics.viewport}px)`)
    .toBeLessThanOrEqual(metrics.viewport + 1);
}

test("factory flow stays usable in RTL on a phone: scope selection, pagination, summary and job follow-up", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockFactoryApi(page);
  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toBeVisible();
  await expectNoHorizontalOverflow(page, "الإعداد الأول");

  await page.getByLabel("المنتج").selectOption(productKey);
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await expect(page.getByLabel("الكتاب للإنتاج")).toBeVisible();
  await page.getByLabel("الكتاب للإنتاج").selectOption(sourceId);
  await expectNoHorizontalOverflow(page, "اختيار المصدر");

  // TOPIC: the topic picker must be in step 2, before the review summary.
  await page.getByLabel("نطاق الإنتاج").selectOption("TOPIC");
  await expect(page.getByLabel("المحور للإنتاج")).toBeVisible();
  await page.getByLabel("المحور للإنتاج").selectOption(topicId);
  await expect(page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" })).toBeEnabled();
  await expectNoHorizontalOverflow(page, "اختيار المحور");

  // SELECTION: search, select a material, move between pages, and preserve selection.
  await page.getByLabel("نطاق الإنتاج").selectOption("SELECTION");
  await expect(page.getByLabel("بحث مواد الإنتاج")).toBeVisible();
  await page.getByText("مادة تجريبية أولى", { exact: true }).locator("xpath=ancestor::label").locator('input[type="checkbox"]').check();
  await expect(page.getByText("صفحة 1 من 2")).toBeVisible();
  await page.getByRole("button", { name: "التالي", exact: true }).click();
  await expect(page.getByText("مادة تجريبية 25", { exact: true })).toBeVisible();
  await expect(page.getByText("1 مادة محددة").first()).toBeVisible();
  await expectNoHorizontalOverflow(page, "اختيار المواد والصفحة الثانية");

  await page.getByRole("button", { name: "السابق", exact: true }).click();
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toBeVisible();
  await expect(page.getByTestId("production-summary")).toContainText("1");
  await expectNoHorizontalOverflow(page, "ملخص الإعداد");

  const start = page.getByTestId("start-production");
  await start.scrollIntoViewIfNeeded();
  await expect(start).toBeInViewport();
  await start.click();
  await expect(page.getByTestId("production-job-details")).toBeVisible();
  await expect(page.getByText("في انتظار بدء التنفيذ")).toBeVisible();
  await expectNoHorizontalOverflow(page, "متابعة المهمة");

  // Repeat the same stages at a desktop width to check responsive layout changes.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expectNoHorizontalOverflow(page, "متابعة المهمة على سطح المكتب");
  await expect(page.getByTestId("production-job-details")).toBeVisible();
});

test("factory load errors remain visible and do not overflow a desktop RTL layout", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockFactoryApi(page, true);
  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toBeVisible();
  await page.getByLabel("المنتج").selectOption(productKey);
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "تعذر تحميل الكتب المتاحة" })).toBeVisible();
  await expect(page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" })).toBeDisabled();
  await expectNoHorizontalOverflow(page, "حالة خطأ تحميل المصدر");
});
