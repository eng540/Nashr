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


test("a product can be created in Control Plane and selected in the factory", async ({ page }) => {
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
  await page.getByLabel("الاسم").fill("E2E UI Product");
  await page.getByLabel("الغرض").fill("Product created through the Control Plane UI");
  await page.getByLabel("الوصفة المنشورة").selectOption("E2E_PRODUCT_RECIPE");
  await page.getByLabel("السياسة المنشورة").selectOption("E2E_PRODUCT_POLICY");
  await page.getByLabel("عقد المخرج المنشور").selectOption("E2E_PRODUCT_CONTRACT");
  await page.getByLabel("التعليمات المنشورة").selectOption("editorial.drafter");
  await page.getByLabel("الهوية التحريرية المنشورة").selectOption("E2E_PRODUCT_IDENTITY");
  await page.getByLabel("الجمهور").fill("E2E audience");
  await page.getByLabel("تجربة المنتج").fill("E2E product experience");
  await page.getByRole("button", { name: "إنشاء ومسودة أولى" }).click();
  await page.getByRole("button", { name: "نشر الإصدار" }).click();
  await expect(page.getByText("تم نشر الإصدار بعد تحقق الخادم.")).toBeVisible();

  const productResponse = await page.request.get("/api/control/products/E2E_UI_PRODUCT");
  expect(productResponse.ok()).toBeTruthy();
  const product = await productResponse.json();
  expect(product.active_version).toBe(1);
  expect(product.versions.some((version: { version: number; status: string }) => version.version === 1 && version.status === "PUBLISHED")).toBeTruthy();

  await page.goto("/posts/workspace");
  await expect(page.getByLabel("المنتج")).toContainText("E2E UI Product · v1");
  await page.getByLabel("المنتج").selectOption("E2E_UI_PRODUCT");
  await expect(page.getByLabel("المنتج")).toHaveValue("E2E_UI_PRODUCT");
});
