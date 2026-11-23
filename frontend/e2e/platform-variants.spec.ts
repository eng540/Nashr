import { expect, test } from "@playwright/test";

test("approved text artifact derives an X platform variant into the DRAFT queue", async ({ page }) => {
  const sourceId = "unit-platform-variant-e2e";
  const textId = "text-platform-variant-e2e";
  const variantId = "variant-platform-variant-e2e";
  const longText = "نص عربي معتمد طويل لاختبار اشتقاق نسخة منصة إكس من بنك المحتوى. ".repeat(10);
  let derived = false;

  const textArtifact = {
    id: textId, source_knowledge_unit_id: sourceId, kind: "TEXT", status: "AVAILABLE",
    content: longText, storage_uri: null, mime_type: "text/plain",
    output_contract_key: "TEST_TEXT_SOURCE", output_contract_version: 1,
    metadata: { source_type: "TEST_SEED", title: "النص المعتمد" },
    review_status: "APPROVED", review_note: null, reviewed_at: "2026-10-17T00:00:00Z",
    created_at: "2026-10-17T00:00:00Z", updated_at: "2026-10-17T00:00:00Z",
  };
  const variantArtifact = () => ({
    ...textArtifact,
    id: variantId,
    content: longText.slice(0, 280),
    output_contract_key: "PLATFORM_VARIANT_X",
    metadata: {
      source_type: "PLATFORM_VARIANT", platform: "x", platform_label_ar: "إكس",
      source_artifact_id: textId, caption: longText.slice(0, 280),
      constraints: { max_text: 280, measure: "x_weighted", measured_length: 280, trimmed: true, provenance: "secondary" },
      notes_ar: ["المنشور 280 حرفًا موزونًا للحسابات غير المدفوعة."],
    },
    review_status: "DRAFT", reviewed_at: null,
  });

  await page.route(/\/api\/artifacts\?review_status=APPROVED.*/, (route) => route.fulfill({ json: [textArtifact] }));
  await page.route(/\/api\/artifacts\?review_status=DRAFT.*/, (route) => route.fulfill({ json: derived ? [variantArtifact()] : [] }));
  await page.route(/\/api\/artifacts\?review_status=REJECTED.*/, (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [] }));
  await page.route(/\/posts\?/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.route(/\/posts\/filter-options/, (route) => route.fulfill({ json: { kinds: [], topics: [], sources: [] } }));
  await page.route(/^https?:\/\/[^/]+\/sources(\/|\?|$)/, (route) => route.fulfill({ json: [] }));
  await page.route(new RegExp("/api/artifacts/" + textId + "/platform-variant$"), async (route) => {
    derived = true;
    const body = route.request().postDataJSON() as { platform: string };
    expect(body.platform).toBe("x");
    await route.fulfill({ status: 201, json: variantArtifact() });
  });

  await page.goto("/bank");
  await page.getByLabel("حالة مراجعة المخرجات").selectOption("APPROVED");
  await expect(page.getByLabel(`منصة النسخة ${textId}`)).toBeVisible();
  await page.getByLabel(`منصة النسخة ${textId}`).selectOption("x");
  await page.getByRole("button", { name: "اشتقاق النسخة" }).click();
  await expect(page.getByText("أُنشئت نسخة إكس وهي الآن قيد المراجعة.")).toBeVisible();

  await page.getByLabel("حالة مراجعة المخرجات").selectOption("DRAFT");
  await expect(page.getByText("نسخة إكس")).toBeVisible();
  await expect(page.getByLabel(`محتوى المخرج ${variantId}`)).toHaveValue(longText.slice(0, 280));
});
