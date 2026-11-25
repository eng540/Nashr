import { expect, test, type Page } from "@playwright/test";

const sourceId = "unit-platform-variant-e2e";
const textId = "text-platform-variant-e2e";
const variantId = "variant-platform-variant-e2e";
const longText = "نص عربي معتمد طويل لاختبار اشتقاق نسخة منصة إكس من بنك المحتوى. ".repeat(10);

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
    adaptation: "length_only", needs_review: true,
    constraints: { max_text: 280, measure: "x_weighted", measured_length: 280, original_length: longText.length, trimmed: true, trim_boundary: "sentence", provenance: "secondary" },
    notes_ar: ["المنشور 280 حرفًا موزونًا للحسابات غير المدفوعة.", "تجهيز طول فقط."],
  },
  review_status: "DRAFT", reviewed_at: null,
});

const cardProducts = [
  {
    id: "prod-card-e2e", key: "arabic-cards", name: "بطاقات عربية باسم طويل جدًا مخصص لاختبار عرض القائمة على الجوال", purpose: "اختبار", active_version: 1,
    versions: [{ version: 1, status: "PUBLISHED", definition: { recipe_key: "card-recipe", output_contract_key: "CARD", policy_key: "POLICY", audience: "عام", experience: "بطاقة", component_versions: { recipe: { key: "card-recipe", version: 1 }, identity: { key: "identity-e2e", version: 1 } } } }],
  },
];
const cardRecipes = [
  { id: "recipe-card-e2e", key: "card-recipe", name: "وصفة البطاقات", purpose: "اختبار", active_version: 1, versions: [{ version: 1, status: "PUBLISHED", stages: [{ key: "render", capability_key: "render_approved_text_card", capability_version: 1 }] }] },
];

async function mockBankRoutes(page: Page, state: { derived: boolean }) {
  await page.route(/\/api\/artifacts\?review_status=APPROVED.*/, (route) => route.fulfill({ json: [textArtifact] }));
  await page.route(/\/api\/artifacts\?review_status=DRAFT.*/, (route) => route.fulfill({ json: state.derived ? [variantArtifact()] : [] }));
  await page.route(/\/api\/artifacts\?review_status=REJECTED.*/, (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: cardProducts }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: cardRecipes }));
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [] }));
  await page.route(/\/posts\?/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.route(/\/posts\/filter-options/, (route) => route.fulfill({ json: { kinds: [], topics: [], sources: [] } }));
  await page.route(/^https?:\/\/[^/]+\/sources(\/|\?|$)/, (route) => route.fulfill({ json: [] }));
}

test("approved text artifact derives an X platform variant into the DRAFT queue", async ({ page }) => {
  const state = { derived: false };
  await mockBankRoutes(page, state);
  await page.route(new RegExp("/api/artifacts/" + textId + "/platform-variant$"), async (route) => {
    state.derived = true;
    const body = route.request().postDataJSON() as { platform: string };
    expect(body.platform).toBe("x");
    await route.fulfill({ status: 201, json: variantArtifact() });
  });

  await page.goto("/bank?library_view=expanded");
  await page.getByLabel("حالة مراجعة المخرجات").selectOption("APPROVED");
  await expect(page.getByLabel(`منصة النسخة ${textId}`)).toBeVisible();
  await page.getByLabel(`منصة النسخة ${textId}`).selectOption("x");
  await page.getByRole("button", { name: "اشتقاق النسخة" }).click();
  await expect(page.getByText("نسخة إكس جاهزة للمراجعة؛ إن كانت موجودة فقد حُفظت تعديلاتك دون استبدالها.")).toBeVisible();

  await page.getByLabel("حالة مراجعة المخرجات").selectOption("DRAFT");
  await expect(page.getByText("نسخة إكس · مقصوصة للحد")).toBeVisible();
  await expect(page.getByLabel(`محتوى المخرج ${variantId}`)).toHaveValue(longText.slice(0, 280));
});

test("approved post derives a platform variant from the bank review view", async ({ page }) => {
  const postId = "post-platform-variant-e2e";
  const approvedPost = { post_id: postId, title: "منشور تجريبي معتمد", content: longText, status: "APPROVED" };
  const state = { derived: false };
  await mockBankRoutes(page, state);
  await page.unroute(/\/posts\?/);
  await page.route(/\/posts\?/, (route) => route.fulfill({ json: { items: [approvedPost], total: 1, limit: 100, offset: 0 } }));
  await page.route(new RegExp("/api/artifacts/post-source/" + postId + "/platform-variant$"), async (route) => {
    state.derived = true;
    const body = route.request().postDataJSON() as { platform: string };
    expect(body.platform).toBe("tiktok");
    const variant = { ...variantArtifact(), metadata: { ...variantArtifact().metadata, platform: "tiktok", platform_label_ar: "تيك توك", source_post_id: postId } };
    await route.fulfill({ status: 201, json: variant });
  });

  await page.goto("/bank?library_view=expanded");
  await page.getByRole("button", {name:"＋ اشتقاق نسخة منصة",exact:true}).click();
  await expect(page.getByLabel("المنشور المصدر للنسخة")).toBeVisible();
  await expect(page.getByText("ينشئ نسخة مراجعة منفصلة", { exact: false })).toContainText("ولا يقصه تلقائياً");
  await page.getByLabel("المنشور المصدر للنسخة").selectOption(postId);
  await page.getByLabel("منصة نسخة المنشور").selectOption("tiktok");
  await page.getByRole("button", { name: "اشتقاق نسخة المنشور" }).click();
  await expect(page.getByText("أُنشئت نسخة تيك توك بحدود الطول من المنشور وهي الآن قيد المراجعة في قائمة المخرجات.")).toBeVisible();
});

test("bank review view keeps the document inside the mobile viewport", async ({ page }) => {
  const state = { derived: false };
  await mockBankRoutes(page, state);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/bank?library_view=expanded");
  const fitsViewport = () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
  await expect(page.getByLabel("حالة مراجعة المخرجات")).toBeVisible();
  expect(await fitsViewport()).toBe(true);

  await page.getByLabel("حالة مراجعة المخرجات").selectOption("APPROVED");
  await expect(page.getByLabel(`منصة النسخة ${textId}`)).toBeVisible();
  await expect(page.getByLabel(`منتج البطاقة ${textId}`)).toBeVisible();
  expect(await fitsViewport()).toBe(true);
});

const variantListItem = {
  id: variantId,
  kind: "TEXT",
  mime_type: "text/plain",
  content: longText,
  platform: "x",
  platform_label_ar: "إكس",
  review_status: "DRAFT",
  excerpt: longText.slice(0, 160),
  full_length: 280,
  adaptation: "length_only",
  needs_review: true,
  source_kind_ar: "مخرج معتمد",
  source_artifact_id: textId,
  source_post_id: null,
  constraints: { max_text: 280, measure: "x_weighted", measured_length: 280, original_length: longText.length, trimmed: true, trim_boundary: "sentence", provenance: "secondary" },
  manual_publication: null,
  created_at: "2026-10-17T00:00:00Z",
};

test("publishing workspace lists platform variants as preparation-only drafts without mobile overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route(/\/api\/artifacts\?review_status=APPROVED.*/, (route) => route.fulfill({ json: [] }));
  await page.route(/\/api\/artifacts\/platform-variants$/, (route) => route.fulfill({ json: [variantListItem] }));
  await page.route(/\/posts\?/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.route(/\/posts\/filter-options/, (route) => route.fulfill({ json: { kinds: [], topics: [], sources: [] } }));
  await page.route(/\/schedules\?limit=/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }));
  await page.route(/\/schedules\/upcoming/, (route) => route.fulfill({ json: { items: [], days: 7, limit: 100 } }));
  await page.route(/\/schedules\/calendar/, (route) => route.fulfill({ json: { date: "2026-10-17", timezone: "Asia/Aden", items: [] } }));
  await page.route(/^https?:\/\/[^/]+\/sources(\/|\?|$)/, (route) => route.fulfill({ json: [] }));
  await page.goto("/publishing");
  await page.getByRole("button", { name: /مسودات المنصات/ }).click();
  const section = page.getByTestId("publishing-platforms");
  await expect(section).toBeVisible();
  await expect(section.getByTestId("platform-variant-card")).toHaveCount(1);
  await expect(section.getByText(/تحضير فقط/)).toBeVisible();
  await expect(section.getByTestId("platform-variant-card").getByText("تتطلب مراجعة")).toBeVisible();
  await expect(section.getByText("ضبط طول فقط، ليست صياغة مخصصة")).toBeVisible();
  await expect(section.getByText(/عند حد جملة/)).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
});

test("approved platform variant can be recorded as manually published without mobile overflow", async ({ page }) => {
  const approvedId = "variant-manual-publication-e2e";
  const approvedVariant = { ...variantListItem, id: approvedId, review_status: "APPROVED", needs_review: false };
  const state: { recorded: { published_at: string; external_url?: string | null } | null } = { recorded: null };
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route(/\/api\/artifacts\?review_status=APPROVED.*/, (route) => route.fulfill({ json: [] }));
  await page.route(/\/api\/artifacts\/platform-variants$/, (route) => route.fulfill({
    json: [state.recorded
      ? { ...approvedVariant, manual_publication: { published_at: state.recorded.published_at, external_url: state.recorded.external_url ?? null, recorded_at: "2026-10-17T12:00:00Z" } }
      : approvedVariant],
  }));
  await page.route(/\/api\/artifacts\/[^/]+\/manual-publication$/, async (route) => {
    state.recorded = route.request().postDataJSON() as { published_at: string; external_url?: string | null };
    await route.fulfill({ json: { id: approvedId, review_status: "APPROVED" } });
  });
  await page.route(/\/posts\?/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.route(/\/posts\/filter-options/, (route) => route.fulfill({ json: { kinds: [], topics: [], sources: [] } }));
  await page.route(/\/schedules\?limit=/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }));
  await page.route(/\/schedules\/upcoming/, (route) => route.fulfill({ json: { items: [], days: 7, limit: 100 } }));
  await page.route(/\/schedules\/calendar/, (route) => route.fulfill({ json: { date: "2026-10-17", timezone: "Asia/Aden", items: [] } }));
  await page.route(/^https?:\/\/[^/]+\/sources(\/|\?|$)/, (route) => route.fulfill({ json: [] }));
  await page.goto("/publishing");
  await page.getByRole("button", { name: /مسودات المنصات/ }).click();
  const section = page.getByTestId("publishing-platforms");
  await expect(section).toBeVisible();
  await expect(section.getByTestId("variant-pipeline-summary")).toContainText("معتمدة بانتظار النشر اليدوي");
  await expect(section.getByText("معتمدة بانتظار النشر اليدوي (1)")).toBeVisible();
  const card = section.getByTestId("platform-variant-card");
  await expect(card).toHaveCount(1);
  await card.getByRole("button", { name: "تسجيل نشر يدوي" }).click();
  await card.getByLabel("تاريخ النشر اليدوي").fill("2026-10-17");
  await card.getByLabel("رابط المنشور").fill("https://x.com/example/status/1");
  await card.getByRole("button", { name: "حفظ التسجيل" }).click();
  await expect(card.getByTestId("manual-publication-record")).toBeVisible();
  await expect(card.getByText(/نُشرت يدويًا خارج التطبيق/)).toBeVisible();
  await expect(card.getByRole("link", { name: "رابط المنشور" })).toBeVisible();
  await expect(section.getByText("منشورة يدويًا (1)")).toBeVisible();
  expect(state.recorded?.published_at).toContain("2026-10-17");
  expect(state.recorded?.external_url).toBe("https://x.com/example/status/1");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
});

test("media platform variant exposes full text copy and on-demand media preview without mobile overflow", async ({ page }) => {
  const mediaVariant = {
    ...variantListItem,
    id: "variant-media-preview-e2e",
    kind: "VIDEO",
    mime_type: "video/mp4",
    platform: "tiktok",
    platform_label_ar: "تيك توك",
    content: longText.slice(0, 200),
    full_length: 200,
    source_kind_ar: "مخرج معتمد",
  };
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route(/\/api\/artifacts\?review_status=APPROVED.*/, (route) => route.fulfill({ json: [] }));
  await page.route(/\/api\/artifacts\/platform-variants$/, (route) => route.fulfill({ json: [mediaVariant] }));
  await page.route(/\/api\/artifacts\/[^/]+\/media-url$/, (route) => route.fulfill({ json: { url: "https://example.com/media/episode.mp4", expires_in: 300 } }));
  await page.route(/\/posts\?/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0 } }));
  await page.route(/\/posts\/filter-options/, (route) => route.fulfill({ json: { kinds: [], topics: [], sources: [] } }));
  await page.route(/\/schedules\?limit=/, (route) => route.fulfill({ json: { items: [], total: 0, limit: 50, offset: 0 } }));
  await page.route(/\/schedules\/upcoming/, (route) => route.fulfill({ json: { items: [], days: 7, limit: 100 } }));
  await page.route(/\/schedules\/calendar/, (route) => route.fulfill({ json: { date: "2026-10-17", timezone: "Asia/Aden", items: [] } }));
  await page.route(/^https?:\/\/[^/]+\/sources(\/|\?|$)/, (route) => route.fulfill({ json: [] }));
  await page.goto("/publishing");
  await page.getByRole("button", { name: /مسودات المنصات/ }).click();
  const card = page.getByTestId("publishing-platforms").getByTestId("platform-variant-card");
  await expect(card).toHaveCount(1);
  await expect(card.getByText("تيك توك")).toBeVisible();
  await card.getByRole("button", { name: "عرض النص الكامل" }).click();
  await expect(card.getByText(longText.slice(0, 200))).toBeVisible();
  await card.getByRole("button", { name: "نسخ النص للنشر اليدوي" }).click();
  await expect(card.getByRole("button", { name: "نُسخ النص" })).toBeVisible();
  await card.getByRole("button", { name: "عرض الوسيط" }).click();
  await expect(card.getByTestId("variant-media-preview").locator("video")).toBeVisible();
  await expect(card.getByRole("link", { name: "فتح الوسيط في تبويب" })).toHaveAttribute("href", "https://example.com/media/episode.mp4");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
});
