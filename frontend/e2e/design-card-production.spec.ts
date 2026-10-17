import { expect, test } from "@playwright/test";

test("approved text can create a card, receive independent visual approval, and enter current Publishing", async ({ page }) => {
  const sourceUnitId = "unit-visual-line-e2e";
  const textId = "text-visual-line-e2e";
  const imageId = "image-visual-line-e2e";
  const postId = "post-visual-line-e2e";
  const approvedText = "نص عربي معتمد للاختبار";
  let imageCreated = false;
  let imageStatus: "DRAFT" | "APPROVED" | "REJECTED" = "DRAFT";
  let attached = false;
  let submittedJob: Record<string, unknown> | null = null;

  const textArtifact = {
    id: textId, source_knowledge_unit_id: sourceUnitId, kind: "TEXT", status: "AVAILABLE",
    content: approvedText, storage_uri: null, mime_type: "text/plain", output_contract_key: "TEXT_ARTIFACT",
    output_contract_version: 1, metadata: { title: "النص المعتمد" }, review_status: "APPROVED",
    review_note: null, reviewed_at: "2026-10-17T00:00:00Z", created_at: "2026-10-17T00:00:00Z", updated_at: "2026-10-17T00:00:00Z",
  };
  const imageArtifact = () => ({
    id: imageId, source_knowledge_unit_id: sourceUnitId, kind: "IMAGE", status: "AVAILABLE",
    content: null, storage_uri: "s3://test-bucket/card.png", mime_type: "image/png",
    output_contract_key: "IMAGE_ARTIFACT", output_contract_version: 1,
    metadata: { title: "بطاقة النص المعتمد", source_artifact_id: textId, source_text_sha256: "a".repeat(64) },
    review_status: imageStatus, review_note: imageStatus === "APPROVED" ? "مراجعة بصرية" : null,
    reviewed_at: imageStatus === "DRAFT" ? null : "2026-10-17T00:00:00Z",
    created_at: "2026-10-17T00:00:00Z", updated_at: "2026-10-17T00:00:00Z",
  });
  const post = () => ({
    post_id: postId, title: "منشور الاختبار", status: "APPROVED", knowledge_unit_id: sourceUnitId,
    topic_id: null, topic_title: null, source_id: "source-visual-line-e2e", source_title: "كتاب الاختبار",
    content: approvedText, content_preview: approvedText, created_at: "2026-10-17T00:00:00Z",
    updated_at: "2026-10-17T00:00:00Z", reviewed_at: "2026-10-17T00:00:00Z", review_note: null,
    published: false, visual_artifact_id: attached ? imageId : null,
  });

  await page.route("**/api/control/products", (route) => route.fulfill({ json: [{
    id: "product-card-e2e", key: "ARABIC_LITERATURE_DESIGN_CARD", name: "بطاقة أدبية عربية",
    purpose: "e2e", active_version: 1, versions: [{
      version: 1, status: "PUBLISHED", definition: {
        recipe_key: "APPROVED_TEXT_TO_DESIGN_CARD", output_contract_key: "IMAGE_ARTIFACT",
        policy_key: "EDITORIAL_DEFAULT", prompt_key: "editorial.drafter", identity_key: "ARABIC_LITERATURE_BASELINE_V1",
        audience: "قرّاء الأدب", experience: "بطاقة نصية معتمدة",
        component_versions: {
          prompt: { key: "editorial.drafter", version_id: "prompt-v1", version: 1 },
          identity: { key: "ARABIC_LITERATURE_BASELINE_V1", version_id: "identity-v1", version: 1 },
          recipe: { key: "APPROVED_TEXT_TO_DESIGN_CARD", version_id: "recipe-v1", version: 1 },
          policy: { key: "EDITORIAL_DEFAULT", version_id: "policy-v1", version: 1 },
          output_contract: { key: "IMAGE_ARTIFACT", version_id: "image-v1", version: 1 },
        },
      },
    }],
  }] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [{
    id: "recipe-card-e2e", key: "APPROVED_TEXT_TO_DESIGN_CARD", name: "بطاقة حتمية", purpose: "e2e",
    active_version: 1, versions: [{ version: 1, status: "PUBLISHED", stages: [{
      key: "render-approved-card", capability_key: "render_approved_text_card", capability_version: 1,
      configuration: { width: 1080, height: 1350, font_family: "naskh", background_mode: "solid" },
    }] }],
  }] }));
  await page.route(/\/api\/artifacts\?review_status=APPROVED$/, (route) => route.fulfill({
    json: [textArtifact, ...(imageCreated && imageStatus === "APPROVED" ? [imageArtifact()] : [])],
  }));
  await page.route(/\/api\/artifacts\?review_status=DRAFT$/, (route) => route.fulfill({
    json: imageCreated && imageStatus === "DRAFT" ? [imageArtifact()] : [],
  }));
  await page.route(/\/api\/artifacts\?review_status=REJECTED$/, (route) => route.fulfill({
    json: imageCreated && imageStatus === "REJECTED" ? [imageArtifact()] : [],
  }));
  await page.route(new RegExp("/api/artifacts/" + imageId + "/media-url$"), (route) => route.fulfill({
    json: { url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jv9sAAAAASUVORK5CYII=", expires_in: 300 },
  }));
  await page.route("**/api/artifacts/*/approve", async (route) => {
    imageStatus = "APPROVED";
    await route.fulfill({ json: imageArtifact() });
  });
  await page.route("**/api/artifacts/*/reject", async (route) => {
    imageStatus = "REJECTED";
    await route.fulfill({ json: imageArtifact() });
  });
  await page.route(/\/(?:api\/)?production-jobs(?:\?.*)?$/, async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } });
    submittedJob = route.request().postDataJSON() as Record<string, unknown>;
    imageCreated = true;
    await route.fulfill({ status: 202, json: { job_id: "visual-card-job-e2e" } });
  });
  await page.route(/\/posts\?/, (route) => route.fulfill({
    json: { items: [post()], total: 1, limit: 20, offset: 0 },
  }));
  await page.route(/\/posts\/filter-options/, (route) => route.fulfill({ json: { kinds: [], topics: [], sources: [] } }));
  await page.route(new RegExp("/posts/" + postId + "/visual-artifact$"), async (route) => {
    attached = true;
    await route.fulfill({ json: post() });
  });
  await page.route(new RegExp("/posts/" + postId + "/visual-artifact/detach$"), async (route) => {
    attached = false;
    await route.fulfill({ json: post() });
  });
  await page.route(/\/(?:api\/)?schedules(?:\/[^?]*)?(?:\?.*)?$/, (route) => route.fulfill({ json: { items: [], total: 0 } }));
  await page.route(/\/(?:api\/)?sources(?:\/[^?]*)?(?:\?.*)?$/, (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [] }));

  await page.goto("/posts/workspace?status=DRAFT");
  // Explicitly select the review workspace instead of relying only on deep-link initialization.
  await page.getByRole("button", { name: /بنك المحتوى والمراجعة/ }).click();
  await expect(page.getByLabel("حالة مراجعة المخرجات")).toBeVisible();
  await page.getByLabel("حالة مراجعة المخرجات").selectOption("APPROVED");
  await expect(page.getByLabel(`منتج البطاقة ${textId}`)).toBeVisible();
  await page.getByLabel(`منتج البطاقة ${textId}`).selectOption("ARABIC_LITERATURE_DESIGN_CARD");
  await page.getByRole("button", { name: "إنتاج البطاقة" }).click();
  await expect(page.getByText("أُنشئت مهمة إنتاج البطاقة: visual-card-job-e2e")).toBeVisible();
  expect(submittedJob).toMatchObject({
    source_artifact_id: textId,
    product_key: "ARABIC_LITERATURE_DESIGN_CARD",
    recipe_key: "APPROVED_TEXT_TO_DESIGN_CARD",
  });

  await page.getByLabel("حالة مراجعة المخرجات").selectOption("DRAFT");
  await expect(page.getByRole("img", { name: "بطاقة النص المعتمد" })).toBeVisible();
  await expect(page.getByRole("button", { name: "اعتماد المخرج", exact: true })).toBeVisible();
  await page.getByLabel(`ملاحظة مراجعة المخرج ${imageId}`).fill("مراجعة بصرية مستقلة");
  await page.getByRole("button", { name: "اعتماد المخرج", exact: true }).click();
  await page.getByLabel("حالة مراجعة المخرجات").selectOption("APPROVED");
  await expect(page.getByText("IMAGE · image/png")).toBeVisible();
  await expect(page.getByText("TEXT · text/plain")).toBeVisible();

  await page.goto("/publishing");
  await expect(page.getByTestId(`ready-post-${postId}`)).toBeVisible();
  await page.getByLabel(`تصميم معتمد لـ منشور الاختبار`).selectOption(imageId);
  await page.getByRole("button", { name: "إرفاق التصميم" }).click();
  await expect(page.getByText("تصميم معتمد مرفق")).toBeVisible();
  await page.getByRole("button", { name: "معاينة التصميم المخزن" }).click();
  await expect(page.getByAltText("معاينة التصميم المعتمد")).toBeVisible();
});
