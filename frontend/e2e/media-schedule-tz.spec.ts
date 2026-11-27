import {libraryFixture} from './libraryFixture';
import { expect, test } from "@playwright/test";

// Runs the media scheduling UI in a NON-Riyadh browser timezone to prove the
// saved instant is anchored to Asia/Riyadh regardless of the browser's zone.
test.use({ timezoneId: "America/New_York" });

test("media draft schedule converts the Riyadh input to UTC independent of browser timezone", async ({ page }) => {
  const imageId = "image-tz-e2e";
  let submitted: Record<string, unknown> | null = null;

  const imageArtifact = {
    id: imageId, source_knowledge_unit_id: "unit-tz-e2e", kind: "IMAGE", status: "AVAILABLE",
    content: null, storage_uri: "s3://test-bucket/tz.png", mime_type: "image/png",
    output_contract_key: "IMAGE_ARTIFACT", output_contract_version: 1,
    metadata: { title: "تصميم اختبار المنطقة الزمنية", caption: "تعليق اختبار", source_type: "MEDIA_BANK_UPLOAD" },
    review_status: "APPROVED", review_note: null, reviewed_at: "2026-10-17T00:00:00Z",
    created_at: "2026-10-17T00:00:00Z", updated_at: "2026-10-17T00:00:00Z",
  };

  await page.route(/\/api\/artifacts(?:\/library)?\?review_status=APPROVED/, (route) => route.fulfill({ json: libraryFixture(route,[imageArtifact]) }));
  await page.route(/\/api\/artifacts(?:\/library)?\?review_status=(DRAFT|REJECTED)/, (route) => route.fulfill({ json: libraryFixture(route,[]) }));
  await page.route(new RegExp("/api/artifacts/" + imageId + "/media-url$"), (route) => route.fulfill({
    json: { url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jv9sAAAAASUVORK5CYII=", expires_in: 300 },
  }));
  await page.route(/\/api\/artifacts\/[^/]+\/schedule$/, async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 201, json: {
      id: "schedule-tz-e2e", name: submitted?.name ?? "", status: "DRAFT", timezone: submitted?.timezone ?? "",
      items: [{ id: "item-tz-e2e", artifact_id: imageId, post_id: null, scheduled_at: submitted?.scheduled_at ?? "", status: "PENDING" }],
    } });
  });
  await page.route(/\/(?:api\/)?schedules(?:\/[^?]*)?(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.route(/^https?:\/\/[^/]+\/(?:api\/)?sources(\/[^?]*)?(\?.*)?$/, (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/identities", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/products", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/control/recipes", (route) => route.fulfill({ json: [] }));

  await page.goto("/bank?library_view=expanded");
  await expect(page.getByLabel("حالة مراجعة المخرجات")).toBeVisible();
  await page.getByLabel("حالة مراجعة المخرجات").selectOption("APPROVED");

  const input = page.getByLabel(`موعد جدولة المخرج ${imageId}`);
  await expect(input).toBeVisible();
  await input.fill("2030-06-15T09:30");
  await page.getByRole("button", { name: "جدولة المسودة" }).click();

  await expect.poll(() => submitted).not.toBeNull();
  // 09:30 Asia/Riyadh (UTC+3) must always serialize to 06:30Z, even in a New York browser.
  expect((submitted as Record<string, unknown>).scheduled_at).toBe("2030-06-15T06:30:00.000Z");
  expect((submitted as Record<string, unknown>).timezone).toBe("Asia/Riyadh");
});
