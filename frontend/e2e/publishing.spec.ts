import { test, expect } from "@playwright/test";

test("approved post can be scheduled through the real API", async ({ page }) => {
  await page.goto("/publishing");
  await expect(page.getByTestId("publishing-workspace")).toBeVisible();

  const checkbox = page.getByRole("checkbox").first();
  await expect(checkbox).toBeVisible();
  await checkbox.check();
  await expect(page.getByTestId("create-plan")).toBeEnabled();

  await page.getByTestId("create-plan").click();
  await expect(page.getByTestId("schedule-panel")).toBeVisible();

  const scheduleResponse = page.waitForResponse((response) =>
    response.url().endsWith("/schedules") && response.request().method() === "POST",
  );

  await page.getByLabel("اسم الخطة").fill("E2E خطة نشر");
  await page.getByLabel("وقت البداية").fill("2030-01-01T12:00");
  await page.getByLabel("الفاصل بالدقائق").fill("60");
  await page.getByTestId("submit-schedule").click();

  const response = await scheduleResponse;
  expect(response.status()).toBe(201);
  const request = response.request().postDataJSON();
  expect(request.post_ids).toHaveLength(1);
  expect(request.name).toBe("E2E خطة نشر");
  await expect(page.getByRole("status")).toContainText("تم إنشاء الخطة بنجاح");
});


test("publishing workspace separates ready, plans, and calendar sections", async ({ page }) => {
  await page.goto("/publishing");
  await expect(page.getByTestId("publishing-workspace")).toBeVisible();

  await expect(page.getByTestId("publishing-ready")).toBeVisible();
  await expect(page.getByLabel("بحث المنشورات الجاهزة")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "أقسام مساحة النشر" })).toContainText("خطط النشر");
  await expect(page.getByRole("navigation", { name: "أقسام مساحة النشر" })).toContainText("التقويم");

  await page.getByRole("button", { name: /خطط النشر/ }).click();
  await expect(page.getByTestId("publishing-plans")).toBeVisible();
  await expect(page.getByLabel("بحث الخطط")).toBeVisible();
  await expect(page.getByLabel("حالة الخطة")).toBeVisible();

  await page.getByRole("button", { name: /التقويم/ }).click();
  await expect(page.getByTestId("publishing-calendar")).toBeVisible();
  await expect(page.getByLabel("تاريخ التقويم")).toBeVisible();
});


test("publishing can attach and preview an approved visual artifact without publishing externally", async ({ page }) => {
  let attached = false;
  const post = () => ({
    post_id: "post-visual-e2e",
    title: "عنوان الاختبار",
    status: "APPROVED",
    knowledge_unit_id: "unit-visual-e2e",
    topic_id: null,
    topic_title: null,
    source_id: "source-visual-e2e",
    source_title: "كتاب الاختبار",
    content: "نص معتمد للاختبار",
    content_preview: "نص معتمد للاختبار",
    created_at: "2026-10-17T00:00:00Z",
    updated_at: "2026-10-17T00:00:00Z",
    reviewed_at: "2026-10-17T00:00:00Z",
    review_note: null,
    published: false,
    visual_artifact_id: attached ? "image-visual-e2e" : null,
  });
  await page.route("**/posts?**", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [post()], total: 1, limit: 20, offset: 0 }) }));
  await page.route("**/posts/filter-options**", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ kinds: [], topics: [], sources: [] }) }));
  await page.route("**/api/artifacts?review_status=APPROVED", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{
    id: "image-visual-e2e", source_knowledge_unit_id: "unit-visual-e2e", kind: "IMAGE", status: "AVAILABLE",
    content: null, storage_uri: "s3://test/card.png", mime_type: "image/png", output_contract_key: "IMAGE_ARTIFACT",
    output_contract_version: 1, metadata: { title: "بطاقة الاختبار" }, review_status: "APPROVED",
    review_note: null, reviewed_at: "2026-10-17T00:00:00Z", created_at: "2026-10-17T00:00:00Z", updated_at: "2026-10-17T00:00:00Z",
  }]) }));
  await page.route("**/posts/post-visual-e2e/visual-artifact", async (route) => {
    attached = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(post()) });
  });
  await page.route("**/posts/post-visual-e2e/visual-artifact/detach", async (route) => {
    attached = false;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(post()) });
  });
  await page.route("**/api/artifacts/image-visual-e2e/media-url", async (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jv9sAAAAASUVORK5CYII=", expires_in: 300 }),
  }));
  await page.goto("/publishing");
  await expect(page.getByTestId("ready-post-post-visual-e2e")).toBeVisible();
  await page.getByLabel("تصميم معتمد لـ عنوان الاختبار").selectOption("image-visual-e2e");
  await page.getByRole("button", { name: "إرفاق التصميم" }).click();
  await expect(page.getByText("تصميم معتمد مرفق")).toBeVisible();
  await page.getByRole("button", { name: "معاينة التصميم المخزن" }).click();
  await expect(page.getByAltText("معاينة التصميم المعتمد")).toBeVisible();
});
