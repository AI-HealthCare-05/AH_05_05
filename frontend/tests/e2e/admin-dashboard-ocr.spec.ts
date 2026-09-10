import { readFile } from 'node:fs/promises';
import { expect, test } from 'playwright/test';

for (const width of [1280, 1600]) {
  test(`백오피스 OCR 취소 건수를 별도 표시하고 조회 실패 시 비운다 (${width})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(() => {
      sessionStorage.setItem('adminAccessToken', 'dashboard-e2e-token');
      sessionStorage.setItem('adminProfile', JSON.stringify({ name: '테스트 관리자', role: 'ADMIN' }));
    });
    await page.route('**/admin-static/**', async (route) => {
      const path = new URL(route.request().url()).pathname.replace('/admin-static/', '');
      const contentTypes: Record<string, string> = {
        html: 'text/html', js: 'text/javascript', css: 'text/css', svg: 'image/svg+xml', png: 'image/png',
      };
      try {
        const body = await readFile(new URL(`../../../app/static/${path}`, import.meta.url));
        await route.fulfill({ body, contentType: contentTypes[path.split('.').pop() ?? ''] ?? 'application/octet-stream' });
      } catch {
        await route.fulfill({ status: 404 });
      }
    });
    let fail = false;
    await page.route('**/api/v1/admin/dashboard/summary?*', async (route) => {
      if (fail) {
        await route.fulfill({ status: 503, json: { message: '집계 조회 실패' } });
        return;
      }
      await route.fulfill({ json: {
        members: {
          total: 10, active: 10, pending: 0, suspended: 0, withdrawn: 0, newSignups: 2,
          totalChangeRate: 0, newSignupsChangeRate: 0, signupTrend: [],
        },
        alarmNotifications: { queued: 0, completed: 0, failed: 0, completedTrend: [] },
        ocrDocuments: { total: 10, queued: 3, completed: 4, failed: 1, cancelled: 2, avgFieldConfidence: 0.95 },
        chatEvaluations: { liked: 0, disliked: 0, unrated: 0, positiveReasons: [], negativeReasons: [] },
      } });
    });
    await page.goto('/admin-static/templates/dashboard.html');
    await expect(page.locator('[data-ocr-cancelled]')).toHaveText('2');
    const card = page.locator('.card').filter({ hasText: 'OCR 문서 처리' });
    await expect(card.getByText('처리·검토 대기', { exact: true })).toBeVisible();
    await expect(card.getByText('등록 완료', { exact: true })).toBeVisible();
    await expect(card.getByText('취소', { exact: true })).toBeVisible();
    const values = await Promise.all(['total', 'queued', 'completed', 'failed', 'cancelled'].map(
      (key) => page.locator(`[data-ocr-${key}]`).innerText(),
    ));
    expect(values).toEqual(['10', '3', '4', '1', '2']);
    expect(await card.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await card.screenshot({ path: testInfo.outputPath('ocr-status.png') });
    fail = true;
    await page.getByRole('button', { name: '30일', exact: true }).click();
    await expect(page.locator('[data-ocr-cancelled]')).toHaveText('—');
    await expect(page.locator('[data-ocr-total]')).toHaveText('—');
  });
}
