import { expect, test } from "@playwright/test";

test("React factory reuses the same production claim key after an ambiguous network failure", async ({ page }) => {
  const sourceId = "11111111-1111-4111-8111-111111111111";
  const materialId = "22222222-2222-4222-8222-222222222222";
  const productKey = "E2E_POST_PRODUCT";
  let submittedKeys: string[] = [];
  let jobId = "33333333-3333-4333-8333-333333333333";

  await page.addInitScript(() => { if (!window.sessionStorage.getItem("e2e-production-claim-cleaned")) { window.localStorage.clear(); window.sessionStorage.setItem("e2e-production-claim-cleaned", "1"); } });
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{
    id: "recipe-id", key: "E2E_POST_RECIPE", name: "E2E Recipe", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", stages: [{ key: "produce", capability_key: "produce_post", capability_version: 1 }] }],
  }] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [{
    id: "product-id", key: productKey, name: "E2E Post Product", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", definition: {
      recipe_key: "E2E_POST_RECIPE", output_contract_key: "TELEGRAM_POST", policy_key: "EDITORIAL_DEFAULT",
      audience: "readers", experience: "post",
    } }],
  }] }));
  await page.route("**/sources**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/book-map")) {
      return route.fulfill({ json: {
        source_id: sourceId, book: { title: "E2E Book", description: "" }, count: 1,
        materials: [{ id: materialId, position: 1, title: "Material", kind: "TEXT", content: "Source text", has_post: false, topic_id: "topic-id" }],
        topics: [{ id: "topic-id", position: 1, title: "Topic", description: "", materials: [{
          id: materialId, position: 1, title: "Material", kind: "TEXT", content: "Source text", has_post: false, topic_id: "topic-id",
        }] }],
      } });
    }
    return route.fulfill({ json: [{
      id: sourceId, filename: "e2e.pdf", book_title: "E2E Book", status: "READY",
      material_count: 1, produced_count: 0, pending_count: 1,
    }] });
  });
  await page.route("**/production-jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as { idempotency_key: string };
    submittedKeys.push(body.idempotency_key);
    if (submittedKeys.length === 1) {
      // Simulate the server having accepted the request while its response is lost.
      await route.abort("connectionreset");
      return;
    }
    await route.fulfill({ status: 202, json: {
      job_id: jobId, source_id: sourceId, status: "COMPLETED", scope: "SOURCE",
      total_items: 1, completed_items: 1, failed_items: 0, pending_items: 0, running_items: 0,
      reconciliation_required_items: 0, current_item_id: null, error_code: null, error_message: null,
      attempts: 1, created_at: "", updated_at: "", started_at: "", completed_at: "",
      progress_percent: 100, next_action: "NONE",
      resolved_prompt: { key: null, version: null, body: null, available: false },
      resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
    } });
  });
  await page.route(`**/production-jobs/${jobId}`, (route) => route.fulfill({ status: 200, json: {
    job_id: jobId, source_id: sourceId, status: "COMPLETED", scope: "SOURCE",
    total_items: 1, completed_items: 1, failed_items: 0, pending_items: 0, running_items: 0,
    reconciliation_required_items: 0, current_item_id: null, error_code: null, error_message: null,
    attempts: 1, created_at: "", updated_at: "", started_at: "", completed_at: "",
    progress_percent: 100, next_action: "NONE",
    resolved_prompt: { key: null, version: null, body: null, available: false },
    resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
  } }));
  await page.route(`**/production-jobs/${jobId}/items**`, (route) => route.fulfill({ json: { job_id: jobId, total: 0, limit: 20, offset: 0, items: [] } }));

  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toBeVisible();
  await page.getByLabel("المنتج").selectOption(productKey);
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await expect(page.getByLabel("الكتاب للإنتاج")).toBeVisible();
  await expect(page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" })).toBeEnabled();
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toBeVisible();
  await expect(page.getByTestId("production-summary")).toContainText("سيشمل الطلب جميع المواد المرتبطة بهذا الكتاب");
  await expect(page.getByTestId("production-summary")).toContainText("المواد الداخلة في الطلب");
  await page.getByTestId("start-production").click();
  await expect(page.getByText(/تعذر بدء الإنتاج/)).toBeVisible();
  expect(submittedKeys).toHaveLength(1);

  // Reload proves the unresolved claim and its selected settings survive a page lifecycle.
  await page.reload();
  await expect(page.getByLabel("المنتج")).toBeVisible();
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await expect(page.getByLabel("الكتاب للإنتاج")).toBeVisible();
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toBeVisible();
  await page.getByTestId("start-production").click();
  await expect(page.getByTestId("production-job-details")).toBeVisible();
  expect(submittedKeys).toHaveLength(2);
  expect(submittedKeys[0]).toBeTruthy();
  expect(submittedKeys[1]).toBe(submittedKeys[0]);

  await page.getByRole("button", { name: /إعداد الإنتاج/ }).click();
  await page.getByTestId("new-production-claim").click();
  await page.getByTestId("start-production").click();
  await expect.poll(() => submittedKeys.length).toBe(3);
  expect(submittedKeys[2]).not.toBe(submittedKeys[0]);
});


test("manual production selection includes materials that have no topic assignment", async ({ page }) => {
  const sourceId = "41111111-1111-4111-8111-111111111111";
  const materialId = "42222222-2222-4222-8222-222222222222";
  const materials = Array.from({ length: 25 }, (_, index) => ({
    id: index === 0 ? materialId : `42222222-2222-4222-8222-${String(index + 1).padStart(12, "0")}`,
    position: index + 1,
    title: index === 0 ? "Unassigned Material" : `Unassigned Material ${index + 1}`,
    kind: "TEXT", content: "Source text", has_post: false, topic_id: null,
  }));
  const productKey = "E2E_POST_PRODUCT";
  await page.addInitScript(() => { window.localStorage.clear(); });
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{
    id: "recipe-id", key: "E2E_POST_RECIPE", name: "E2E Recipe", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", stages: [{ key: "produce", capability_key: "produce_post", capability_version: 1 }] }],
  }] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [{
    id: "product-id", key: productKey, name: "E2E Post Product", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", definition: {
      recipe_key: "E2E_POST_RECIPE", output_contract_key: "TELEGRAM_POST", policy_key: "EDITORIAL_DEFAULT",
      audience: "readers", experience: "post",
    } }],
  }] }));
  await page.route("**/sources**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/book-map")) {
      return route.fulfill({ json: {
        source_id: sourceId, book: { title: "Legacy Book", description: "" }, count: materials.length,
        topics: [], materials,
      } });
    }
    return route.fulfill({ json: [{
      id: sourceId, filename: "legacy.pdf", book_title: "Legacy Book", status: "READY",
      material_count: materials.length, produced_count: 0, pending_count: materials.length,
    }] });
  });
  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toBeVisible();
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await expect(page.getByLabel("الكتاب للإنتاج")).toBeVisible();
  await page.getByLabel("نطاق الإنتاج").selectOption("SELECTION");
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByText("Unassigned Material", { exact: true })).toBeVisible();
  await expect(page.getByLabel("بحث مواد الإنتاج")).toBeVisible();
  await expect(page.getByText("صفحة 1 من 2")).toBeVisible();
  await page.getByText("Unassigned Material", { exact: true }).locator("xpath=ancestor::label").locator('input[type="checkbox"]').check();
  await expect(page.getByText("1 مادة محددة").first()).toBeVisible();
  await page.getByLabel("بحث مواد الإنتاج").fill("Material 25");
  await expect(page.getByText("Unassigned Material 25", { exact: true })).toBeVisible();
  await expect(page.getByText(/توجد اختيارات محفوظة خارج الفلتر الحالي/)).toBeVisible();
  await page.getByLabel("بحث مواد الإنتاج").fill("");
  await expect(page.getByText("صفحة 1 من 2")).toBeVisible();
  await page.getByRole("button", { name: "التالي", exact: true }).click();
  await expect(page.getByText("Unassigned Material 25", { exact: true })).toBeVisible();
  await expect(page.getByText("1 مادة محددة").first()).toBeVisible();
  await page.getByRole("button", { name: "السابق", exact: true }).click();
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toContainText("1");

  await page.getByRole("button", { name: /بنك المحتوى والمراجعة/ }).click();
  await expect(page.getByTestId("post-bank-filters")).toBeVisible();
  await expect(page.getByTestId("production-panel")).toHaveCount(0);
  await page.getByRole("button", { name: /إعداد الإنتاج/ }).click();
  await expect(page.getByTestId("production-summary")).toBeVisible();
});


test("production wizard selects SOURCE, TOPIC and SELECTION before review and submits the reviewed payload", async ({ page }) => {
  const sourceId = "51111111-1111-4111-8111-111111111111";
  const topicId = "52222222-2222-4222-8222-222222222222";
  const assignedId = "53333333-3333-4333-8333-333333333333";
  const unassignedId = "54444444-4444-4444-8444-444444444444";
  const productKey = "E2E_REVIEWED_PRODUCT";
  const identityKey = "E2E_REVIEWED_IDENTITY";
  const materials = [
    { id: assignedId, position: 1, title: "Assigned material", kind: "TEXT", content: "Assigned text", has_post: false, topic_id: topicId },
    { id: unassignedId, position: 2, title: "Unassigned material", kind: "TEXT", content: "Unassigned text", has_post: false, topic_id: null },
    ...Array.from({ length: 22 }, (_, index) => ({
      id: `55555555-5555-4555-8555-${String(index + 1).padStart(12, "0")}`,
      position: index + 3, title: `Additional material ${index + 1}`, kind: index % 2 ? "TEXT" : "HTML",
      content: "Additional text", has_post: false, topic_id: null,
    })),
  ];
  const submitted: Array<Record<string, unknown>> = [];
  await page.addInitScript(() => { window.localStorage.clear(); });
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [{
    id: "identity-id", key: identityKey, name: "E2E Identity", purpose: "test", active_version: 1, versions: [{ version: 1, status: "PUBLISHED" }],
  }] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{
    id: "recipe-id", key: "E2E_REVIEWED_RECIPE", name: "E2E Recipe", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", stages: [{ key: "produce", capability_key: "produce_post", capability_version: 1 }] }],
  }] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [{
    id: "product-id", key: productKey, name: "Reviewed Product", purpose: "test", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", definition: {
      recipe_key: "E2E_REVIEWED_RECIPE", output_contract_key: "TELEGRAM_POST", policy_key: "EDITORIAL_DEFAULT", audience: "readers", experience: "post",
    } }],
  }] }));
  await page.route("**/sources**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/book-map")) return route.fulfill({ json: {
      source_id: sourceId, book: { title: "Reviewed Book", description: "" }, count: materials.length,
      materials,
      topics: [{ id: topicId, position: 1, title: "Reviewed Topic", description: "", materials: [materials[0]] }],
    } });
    return route.fulfill({ json: [{
      id: sourceId, filename: "reviewed.pdf", book_title: "Reviewed Book", status: "READY",
      material_count: materials.length, produced_count: 0, pending_count: materials.length,
    }] });
  });
  await page.route("**/production-jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submitted.push(route.request().postDataJSON() as Record<string, unknown>);
    const body = submitted[submitted.length - 1];
    await route.fulfill({ status: 202, json: {
      job_id: `job-${submitted.length}`, source_id: sourceId, status: "QUEUED", scope: body.scope,
      total_items: 1, completed_items: 0, failed_items: 0, pending_items: 1, running_items: 0, reconciliation_required_items: 0,
      current_item_id: null, error_code: null, error_message: null, attempts: 0, created_at: "", updated_at: "", started_at: null,
      completed_at: null, progress_percent: 0, next_action: "WAIT",
      resolved_prompt: { key: null, version: null, body: null, available: false },
      resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
    } });
  });
  await page.route("**/production-jobs/job-*/items**", (route) => route.fulfill({ json: { job_id: "job", total: 0, limit: 20, offset: 0, items: [] } }));
  await page.route("**/production-jobs/job-*", (route) => route.fulfill({ status: 200, json: {
    job_id: "job", source_id: sourceId, status: "QUEUED", scope: "SOURCE", total_items: 1, completed_items: 0, failed_items: 0,
    pending_items: 1, running_items: 0, reconciliation_required_items: 0, current_item_id: null, error_code: null, error_message: null,
    attempts: 0, created_at: "", updated_at: "", started_at: null, completed_at: null, progress_percent: 0, next_action: "WAIT",
    resolved_prompt: { key: null, version: null, body: null, available: false },
    resolved_context: { available: false, invalid: false, schema_version: null, origin: null, captured_at: null, prompt_template: null },
  } }));
  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toBeVisible();
  await page.getByLabel("المنتج").selectOption(productKey);
  await page.getByLabel("الهوية التحريرية للإنتاج").selectOption(identityKey);
  await page.getByRole("button", { name: "متابعة إلى اختيار المصدر" }).click();
  await expect(page.getByLabel("الكتاب للإنتاج")).toBeVisible();
  await page.getByLabel("الكتاب للإنتاج").selectOption(sourceId);

  // SOURCE: review is reached only after source/book-map data is ready.
  await expect(page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" })).toBeEnabled();
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toContainText("الكتاب كاملًا");
  await expect(page.getByTestId("production-summary")).toContainText(String(materials.length));
  await page.getByTestId("start-production").click();
  await expect(page.getByTestId("production-job-details")).toBeVisible();
  expect(submitted[0]).toMatchObject({ source_id: sourceId, scope: "SOURCE", product_key: productKey, identity_key: identityKey });
  expect(submitted[0].idempotency_key).toBeTruthy();
  expect(submitted[0]).not.toHaveProperty("topic_id");
  expect(submitted[0]).not.toHaveProperty("knowledge_unit_ids");

  // TOPIC: topic selection is in step 2 and precedes the review step.
  await page.getByRole("button", { name: /إعداد الإنتاج/ }).click();
  await page.getByRole("button", { name: "تعديل المصدر والنطاق" }).click();
  await page.getByLabel("نطاق الإنتاج").selectOption("TOPIC");
  await expect(page.getByLabel("المحور للإنتاج")).toBeVisible();
  await expect(page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" })).toBeDisabled();
  await page.getByLabel("المحور للإنتاج").selectOption(topicId);
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toContainText("محور: Reviewed Topic");
  await expect(page.getByTestId("production-summary")).toContainText("1");
  await page.getByTestId("start-production").click();
  await expect(page.getByTestId("production-job-details")).toBeVisible();
  expect(submitted[1]).toMatchObject({ source_id: sourceId, scope: "TOPIC", topic_id: topicId, product_key: productKey, identity_key: identityKey });
  expect(submitted[1].idempotency_key).toBeTruthy();
  expect(submitted[1]).not.toHaveProperty("knowledge_unit_ids");

  // SELECTION: linked and unassigned materials can be chosen across pages and filters.
  await page.getByRole("button", { name: /إعداد الإنتاج/ }).click();
  await page.getByRole("button", { name: "تعديل المصدر والنطاق" }).click();
  await page.getByLabel("نطاق الإنتاج").selectOption("SELECTION");
  await expect(page.getByLabel("بحث مواد الإنتاج")).toBeVisible();
  await page.getByLabel("بحث مواد الإنتاج").fill("Assigned material");
  await page.getByText("Assigned material", { exact: true }).locator("xpath=ancestor::label").locator('input[type="checkbox"]').check();
  await page.getByLabel("بحث مواد الإنتاج").fill("Unassigned material");
  await page.getByText("Unassigned material", { exact: true }).locator("xpath=ancestor::label").locator('input[type="checkbox"]').check();
  await page.getByLabel("بحث مواد الإنتاج").fill("");
  await page.getByLabel("نوع المادة للإنتاج").selectOption("HTML");
  await page.getByLabel("نوع المادة للإنتاج").selectOption("");
  await page.getByRole("button", { name: "متابعة إلى مراجعة إعداد الإنتاج" }).click();
  await expect(page.getByTestId("production-summary")).toContainText("مواد محددة");
  await expect(page.getByTestId("production-summary")).toContainText("2");
  await expect(page.getByTestId("production-summary")).toContainText(assignedId);
  await expect(page.getByTestId("production-summary")).toContainText(unassignedId);
  await page.getByTestId("start-production").click();
  await expect(page.getByTestId("production-job-details")).toBeVisible();
  expect(submitted[2]).toMatchObject({ source_id: sourceId, scope: "SELECTION", product_key: productKey, identity_key: identityKey, knowledge_unit_ids: [assignedId, unassignedId] });
  expect(submitted[2].idempotency_key).toBeTruthy();
});
