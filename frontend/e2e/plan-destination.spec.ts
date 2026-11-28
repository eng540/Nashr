import { test, expect } from '@playwright/test';

const plan = (id: string, destination: string | null, platform = 'telegram') => ({
  id, name: 'خطة محفوظة ' + id, platform, destination_label: destination, status: 'DRAFT',
  timezone: 'Asia/Riyadh', total_items: 1, pending_items: 1, published_items: 0, failed_items: 0,
  next_scheduled_at: null, items: [{ id: 'item-' + id, position: 1, title: 'مادة للمراجعة', status: 'PENDING',
    scheduled_at: '2032-01-02T10:00:00Z', content_preview: 'نص محفوظ، لا نشر من فتح الخطة.', post_id: 'post-' + id }],
});
for (const width of [320, 390, 1280]) test(`selected plan shows its own destination before actions at ${width}px`, async ({ page }, info) => {
  const writes: string[] = [];
  const first = plan('first', 'قناة خاصة · وجهة محفوظة');
  const second = plan('second', 'قناة مختلفة');
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (request.method() !== 'GET') { writes.push(path); return route.abort(); }
    if (path === '/schedules/first') return route.fulfill({ json: first });
    if (path === '/schedules/second') { await new Promise(r => setTimeout(r, 150)); return route.fulfill({ json: second }); }
    if (path === '/schedules') return route.fulfill({ json: { items: [first, second], total: 2, offset: 0, limit: 20 } });
    if (path === '/sources' || path === '/api/artifacts/platform-variants') return route.fulfill({ json: [] });
    if (path.startsWith('/api/') || path.startsWith('/posts') || path.startsWith('/schedules')) return route.fulfill({ json: { items: [], total: 0 } });
    return route.continue();
  });
  await page.setViewportSize({ width, height: 844 });
  await page.goto('/publishing?view=plans&schedule_id=first&audit_keep=preserved');
  const detail = page.getByTestId('schedule-detail');
  const destination = detail.getByLabel('وجهة الخطة المحددة', { exact: true });
  await expect(destination).toHaveText('Telegram · قناة خاصة · وجهة محفوظة');
  const heading = detail.getByRole('heading', { name: first.name, exact: true });
  await expect(heading).toBeVisible();
  const actions = detail.getByRole('button', { name: 'تفعيل النشر الآلي', exact: true });
  await expect(actions).toBeVisible();
  expect(await destination.evaluate((node) => !!(node.compareDocumentPosition(Array.from(node.closest('section')!.querySelectorAll('button')).find(b => b.textContent === 'تفعيل النشر الآلي')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBeTruthy();
  await detail.screenshot({ path: info.outputPath('destination-' + width + '.png'), style: 'header{visibility:hidden}' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByTestId('publishing-plans').getByRole('button', { name: /خطة محفوظة second/ }).click();
  await expect(detail).toHaveCount(0);
  await expect(destination).toHaveText('Telegram · قناة مختلفة');
  await expect(detail).not.toContainText('قناة خاصة');
  expect(new URL(page.url()).searchParams.get('audit_keep')).toBe('preserved');
  await page.reload();
  await expect(destination).toHaveText('Telegram · قناة مختلفة');
  expect(writes).toEqual([]);
});
for (const destination of [null, '', '   ']) test(`missing destination remains explicit ${JSON.stringify(destination)}`, async ({ page }) => {
  await page.route('**/*', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/schedules/missing') return route.fulfill({ json: plan('missing', destination, '') });
    if (path === '/schedules') return route.fulfill({ json: { items: [plan('missing', 'لا تستخدم وجهة القائمة')], total: 1 } });
    if (path.startsWith('/api/') || path.startsWith('/posts') || path.startsWith('/schedules')) return route.fulfill({ json: { items: [], total: 0 } });
    return route.continue();
  });
  await page.goto('/publishing?schedule_id=missing');
  await expect(page.getByTestId('schedule-detail').getByLabel('وجهة الخطة المحددة')).toHaveText('منصة غير موضحة · لا توجد وجهة محفوظة موضحة لهذه الخطة');
  await expect(page.getByTestId('schedule-detail')).not.toContainText('لا تستخدم وجهة القائمة');
});
