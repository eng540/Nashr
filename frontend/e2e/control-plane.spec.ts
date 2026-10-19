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
  await expect(page.getByLabel("نص التعليمات")).toHaveValue("E2E prompt body");
  await expect(page.getByText(/الإصدار المنشور:.*v1/)).toBeVisible();
});


test("Control Plane can publish the approved-text card recipe capability", async ({ page }) => {
  await page.goto("/control");
  await expect(page.getByRole("button", { name: "المنتجات" })).toBeEnabled();
  await page.getByRole("button", { name: "الوصفات" }).click();
  await page.getByRole("button", { name: "جديد" }).click();
  await page.getByLabel("المفتاح").fill("E2E_APPROVED_TEXT_CARD_RECIPE");
  await expect(page.getByLabel("المفتاح")).toHaveValue("E2E_APPROVED_TEXT_CARD_RECIPE");
  await page.getByLabel("الاسم").fill("E2E Approved Text Card Recipe");
  await expect(page.getByLabel("الاسم")).toHaveValue("E2E Approved Text Card Recipe");
  await page.getByLabel("الغرض").fill("Verify card capability is configurable through Control Plane");
  await expect(page.getByLabel("الغرض")).toHaveValue("Verify card capability is configurable through Control Plane");
  await page.getByLabel("القدرة").first().selectOption("render_approved_text_card");
  await expect(page.getByLabel("القدرة").first()).toHaveValue("render_approved_text_card");
  const createRecipeButton = page.getByRole("button", { name: "إنشاء ومسودة أولى" });
  await expect(createRecipeButton).toBeEnabled();
  await createRecipeButton.click();
  await expect(page.getByText("تم إنشاء العنصر ومسودته الأولى.")).toBeVisible();
  await page.getByRole("button", { name: "نشر الإصدار" }).click();
  await expect(page.getByText("تم نشر الإصدار بعد تحقق الخادم.")).toBeVisible();
  const recipeResponse = await page.request.get("/api/control/recipes/E2E_APPROVED_TEXT_CARD_RECIPE");
  expect(recipeResponse.ok()).toBeTruthy();
  const recipe = await recipeResponse.json();
  const published = recipe.versions.find((version: { status: string }) => version.status === "PUBLISHED");
  expect(published.stages).toEqual([
    expect.objectContaining({ capability_key: "render_approved_text_card", capability_version: 1 }),
  ]);
});

test("a product can be created in Control Plane and selected in the factory", async ({ page }) => {
  const promptsResponse = await page.request.get("/api/control/prompts");
  expect(promptsResponse.ok()).toBeTruthy();
  const promptItems = await promptsResponse.json();
  const promptMeta = promptItems.find((prompt: { name: string; key: string }) => prompt.name === "E2E Control Prompt");
  expect(promptMeta).toBeTruthy();
  const promptDetailResponse = await page.request.get("/api/control/prompts/" + encodeURIComponent(promptMeta.key));
  expect(promptDetailResponse.ok()).toBeTruthy();
  const promptDetail = await promptDetailResponse.json();
  const promptKey = promptDetail.key as string;
  expect(promptDetail.active_version).not.toBeNull();

  const recipe = await page.request.post("/api/control/recipes", { data: {
    key: "E2E_PRODUCT_RECIPE",
    name: "E2E Product Recipe",
    purpose: "Recipe fixture for Control Plane UI",
    stages: [{ key: "produce-post", capability_key: "produce_post", capability_version: 1, configuration: {} }],
  } });
  expect(recipe.ok()).toBeTruthy();
  expect((await page.request.post("/api/control/recipes/E2E_PRODUCT_RECIPE/versions/1/publish")).ok()).toBeTruthy();

  const policy = await page.request.post("/api/control/policies", { data: {
    key: "E2E_PRODUCT_POLICY",
    name: "E2E Product Policy",
    purpose: "Policy fixture for Control Plane UI",
    definition: { min_content_chars: 1, max_content_chars: 100000, required_terms: [], forbidden_terms: [], allow_urls: true },
  } });
  expect(policy.ok()).toBeTruthy();
  expect((await page.request.post("/api/control/policies/E2E_PRODUCT_POLICY/versions/1/publish")).ok()).toBeTruthy();

  const contract = await page.request.post("/api/control/output-contracts", { data: {
    key: "E2E_PRODUCT_CONTRACT",
    name: "E2E Product Contract",
    purpose: "Output contract fixture for Control Plane UI",
    definition: { artifact_kind: "POST", mime_type: "text/plain", content_mode: "INLINE", required_metadata_fields: [], max_content_chars: 10000 },
  } });
  expect(contract.ok()).toBeTruthy();
  expect((await page.request.post("/api/control/output-contracts/E2E_PRODUCT_CONTRACT/versions/1/publish")).ok()).toBeTruthy();

  const identity = await page.request.post("/api/control/identities", { data: {
    key: "E2E_PRODUCT_IDENTITY",
    name: "E2E Product Identity",
    purpose: "Identity fixture for immutable product manifest",
    definition: {
      purpose: "Create accurate and source-grounded Arabic educational content",
      audience: "Arabic language learners",
      voice: "Careful language educator",
      tone: "Clear and precise",
      principles: ["Preserve meaning"],
      objectives: ["Teach the correct usage"],
      constraints: ["Do not invent linguistic claims"],
    },
  } });
  expect(identity.ok()).toBeTruthy();
  expect((await page.request.post("/api/control/identities/E2E_PRODUCT_IDENTITY/versions/1/publish")).ok()).toBeTruthy();

  await page.goto("/control");
  await page.getByRole("button", { name: "جديد" }).click();
  await page.getByLabel("المفتاح").fill("E2E_UI_PRODUCT");
  await expect(page.getByLabel("المفتاح")).toHaveValue("E2E_UI_PRODUCT");
  await page.getByLabel("الاسم").fill("E2E UI Product");
  await expect(page.getByLabel("الاسم")).toHaveValue("E2E UI Product");
  await page.getByLabel("الغرض").fill("Product created through the Control Plane UI");
  await expect(page.getByLabel("الغرض")).toHaveValue("Product created through the Control Plane UI");
  await page.getByLabel("الوصفة").selectOption("E2E_PRODUCT_RECIPE");
  await page.getByLabel("السياسة").selectOption("E2E_PRODUCT_POLICY");
  await page.getByLabel("عقد المخرج").selectOption("E2E_PRODUCT_CONTRACT");
  await page.getByLabel("التعليمات").selectOption(promptKey);
  await expect(page.getByLabel("التعليمات")).toHaveValue(promptKey);
  await page.getByLabel("الهوية التحريرية").selectOption("E2E_PRODUCT_IDENTITY");
  await expect(page.getByLabel("الهوية التحريرية")).toHaveValue("E2E_PRODUCT_IDENTITY");
  await page.getByLabel("الجمهور").fill("E2E audience");
  await page.getByLabel("تجربة المنتج").fill("E2E product experience");
  const createProductButton = page.getByRole("button", { name: "إنشاء ومسودة أولى" });
  await expect(createProductButton).toBeEnabled();
  await createProductButton.click();
  await page.getByRole("button", { name: "نشر الإصدار" }).click();
  await expect(page.getByText("تم نشر الإصدار بعد تحقق الخادم.")).toBeVisible();

  const productResponse = await page.request.get("/api/control/products/E2E_UI_PRODUCT");
  expect(productResponse.ok()).toBeTruthy();
  const product = await productResponse.json();
  expect(product.active_version).toBe(1);
  const publishedProductVersion = product.versions.find((version: { version: number; status: string }) => version.version === 1 && version.status === "PUBLISHED");
  expect(publishedProductVersion).toBeTruthy();
  expect(publishedProductVersion.definition.prompt_key).toBe(promptKey);
  expect(publishedProductVersion.definition.identity_key).toBe("E2E_PRODUCT_IDENTITY");

  // Publish a new contract version, then explicitly pin it to a new product version.
  const contractV2 = await page.request.post("/api/control/output-contracts/E2E_PRODUCT_CONTRACT/versions", { data: {
    definition: {
      artifact_kind: "POST",
      mime_type: "text/plain",
      content_mode: "INLINE",
      required_metadata_fields: ["source", "title"],
      max_content_chars: 10000,
    },
  } });
  expect(contractV2.ok()).toBeTruthy();
  expect((await page.request.post("/api/control/output-contracts/E2E_PRODUCT_CONTRACT/versions/2/publish")).ok()).toBeTruthy();

  await page.reload();
  await expect(page.getByRole("button", { name: "المنتجات" })).toBeEnabled();
  await page.getByRole("button", { name: /E2E_UI_PRODUCT/ }).click();
  await expect(page.getByLabel("المفتاح")).toHaveValue("E2E_UI_PRODUCT");
  await page.getByRole("button", { name: "إنشاء مسودة من هذا الإصدار" }).click();
  await expect(page.getByText("تم إنشاء مسودة إصدار جديدة من الإصدار المحدد.")).toBeVisible();
  await expect(page.getByLabel("إصدار عقد المخرج")).toBeVisible();
  await page.getByLabel("إصدار عقد المخرج").selectOption("2");
  await expect(page.getByLabel("إصدار عقد المخرج")).toHaveValue("2");
  await page.getByRole("button", { name: "حفظ / إنشاء مسودة" }).click();
  await expect(page.getByText("تم حفظ تعديلات المسودة.")).toBeVisible();
  await page.getByRole("button", { name: "نشر الإصدار" }).click();
  await expect(page.getByText("تم نشر الإصدار بعد تحقق الخادم.")).toBeVisible();

  const upgradedProductResponse = await page.request.get("/api/control/products/E2E_UI_PRODUCT");
  expect(upgradedProductResponse.ok()).toBeTruthy();
  const upgradedProduct = await upgradedProductResponse.json();
  const upgradedV2 = upgradedProduct.versions.find((version: { version: number; status: string }) => version.version === 2 && version.status === "PUBLISHED");
  expect(upgradedV2.definition.component_versions.output_contract.version).toBe(2);
  const originalV1 = upgradedProduct.versions.find((version: { version: number }) => version.version === 1);
  expect(originalV1.definition.component_versions.output_contract.version).toBe(1);

  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toContainText("E2E UI Product · v1");
  await page.getByLabel("المنتج").selectOption("E2E_UI_PRODUCT");
  await expect(page.getByLabel("المنتج")).toHaveValue("E2E_UI_PRODUCT");
});

test("a published product can be derived independently with pinned components reused", async ({ page }) => {
  const sourceKey = "ARABIC_LITERATURE_TELEGRAM_POST";
  const sourceResponse = await page.request.get("/api/control/products/" + sourceKey);
  expect(sourceResponse.ok()).toBeTruthy();
  const source = await sourceResponse.json();
  const sourceVersion = source.versions.find((version: { version: number; status: string }) => version.version === source.active_version);
  expect(sourceVersion?.definition.component_versions).toBeTruthy();

  await page.goto("/control");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: new RegExp(sourceKey) }).click();
  await page.waitForLoadState("networkidle");
  // Explicitly select the source version in the Control Plane before deriving.
  await page.getByLabel("الإصدار").selectOption(String(source.active_version));
  await expect(page.getByLabel("الإصدار")).toHaveValue(String(source.active_version));
  await expect(page.getByRole("button", { name: "اشتقاق منتج مستقل" })).toBeEnabled();
  await page.getByRole("button", { name: "اشتقاق منتج مستقل" }).click();
  const derivedKey = "E2E_DERIVED_" + Date.now();
  await page.getByLabel("مفتاح المنتج المشتق").fill(derivedKey);
  await page.getByLabel("اسم المنتج المشتق").fill("E2E derived product");
  await page.getByLabel("غرض المنتج المشتق").fill("Verify independent product lineage and exact component reuse");
  await page.getByRole("button", { name: "إنشاء المنتج المشتق" }).click();

  await expect(page.getByText("سجل اشتقاق المنتج")).toBeVisible();
  await expect(page.locator("strong").filter({ hasText: sourceKey })).toBeVisible();

  const alternatePromptKey = "E2E_DERIVED_PROMPT_" + Date.now();
  const prompt = await page.request.post("/api/control/prompts", { data: {
    key: alternatePromptKey,
    name: "Derived product alternate prompt",
    purpose: "Verify a single component change is surfaced accurately.",
    body: "Alternative prompt for the derived product only.",
  } });
  expect(prompt.ok()).toBeTruthy();
  expect((await page.request.post("/api/control/prompts/" + alternatePromptKey + "/versions/1/publish")).ok()).toBeTruthy();

  // Refresh the Control Plane's hydrated prompt list, then wait for its async
  // initial load to finish before selecting the derived draft. Otherwise reload()
  // can still replace the just-edited form with the persisted prompt value.
  await page.reload();
  await expect(page.getByRole("button", { name: "المنتجات" })).toBeEnabled();
  await expect(page.getByLabel("التعليمات").locator('option[value="' + alternatePromptKey + '"]')).toHaveCount(1);
  await page.getByRole("button", { name: new RegExp(derivedKey) }).click();
  // Wait for the asynchronous product-detail fetch to hydrate the selected form
  // before interacting with it; otherwise the response can overwrite the edit.
  await expect(page.getByLabel("المفتاح")).toHaveValue(derivedKey);
  await expect(page.getByLabel("التعليمات")).toBeEnabled();
  await expect(page.getByLabel("التعليمات").locator('option[value="' + alternatePromptKey + '"]')).toHaveCount(1);
  await page.getByLabel("التعليمات").selectOption(alternatePromptKey);
  await expect(page.getByLabel("التعليمات")).toHaveValue(alternatePromptKey);
  await page.getByRole("button", { name: "حفظ / إنشاء مسودة" }).click();
  await expect(page.getByText("تم حفظ تعديلات المسودة.")).toBeVisible();
  const savedDraftResponse = await page.request.get("/api/control/products/" + derivedKey);
  expect(savedDraftResponse.ok()).toBeTruthy();
  const savedDraftProduct = await savedDraftResponse.json();
  expect(savedDraftProduct.versions.find((version: { status: string }) => version.status === "DRAFT")?.definition.prompt_key).toBe(alternatePromptKey);
  await page.getByRole("button", { name: "نشر الإصدار" }).click();
  await expect(page.getByText("تم نشر الإصدار بعد تحقق الخادم.")).toBeVisible();
  // Re-fetch persisted lineage/diff state, rather than asserting only transient form state.
  await page.reload();
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: new RegExp(derivedKey) }).click();
  await page.waitForLoadState("networkidle");
  const derivedResponse = await page.request.get("/api/control/products/" + derivedKey);
  expect(derivedResponse.ok()).toBeTruthy();
  const derived = await derivedResponse.json();
  expect(derived.derivation.parent_product_key).toBe(sourceKey);
  expect(derived.derivation.source_version).toBe(source.active_version);
  expect(derived.derivation.changes.prompt_key).toEqual({
    from: sourceVersion.definition.prompt_key,
    to: alternatePromptKey,
  });
  expect(derived.derivation.component_diffs.prompt.from).toEqual(sourceVersion.definition.component_versions.prompt);
  expect(derived.derivation.component_diffs.prompt.to.key).toBe(alternatePromptKey);
  expect(derived.derivation.component_diffs.prompt.to.version).toBe(1);
  await expect(page.getByText("تغييرات المكونات المثبتة")).toBeVisible();
  await expect(page.locator("p").filter({ hasText: "مرجع المشتق:" }).filter({ hasText: alternatePromptKey })).toBeVisible();
  for (const component of ["identity", "recipe", "policy", "output_contract"]) {
    expect(derived.derivation.component_diffs[component]).toBeUndefined();
    expect(derived.versions.find((version: { status: string }) => version.status === "PUBLISHED")?.definition.component_versions[component]).toEqual(sourceVersion.definition.component_versions[component]);
  }
  await expect(page.getByText("مرجع الأصل:", { exact: false })).toBeVisible();
  await expect(page.getByText("مرجع المشتق:", { exact: false })).toBeVisible();
  await expect(
    page.locator("p").filter({ hasText: "مرجع الأصل:" }).filter({ hasText: sourceVersion.definition.component_versions.prompt.key }),
  ).toBeVisible();
  await expect(
    page.locator("p").filter({ hasText: "مرجع المشتق:" }).filter({ hasText: alternatePromptKey }),
  ).toBeVisible();

  const sourceAfter = await (await page.request.get("/api/control/products/" + sourceKey)).json();
  const sourceVersionAfter = sourceAfter.versions.find((version: { version: number }) => version.version === source.active_version);
  expect(sourceVersionAfter.definition).toEqual(sourceVersion.definition);
});
