import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.use({ timezoneId: 'UTC' });

for (const { width, hospital } of [
  { width: 320, hospital: '스타이비인후과' },
  { width: 390, hospital: '스타이비인후과' },
  { width: 320, hospital: 'InternationalMedicalCenterOtorhinolaryngologyDepartment' },
]) {
  test(`${width}px ${hospital} upcoming visit shows hospital once and still opens the correct editor`, async ({ page }, testInfo) => {
    test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
    await page.setViewportSize({ width, height: 812 });
    await page.clock.setFixedTime(new Date('2026-09-08T03:00:00Z'));
    await page.route('**/api/v1/**', (route) => route.abort());
    const visits = [
      { id: 71, user_id: 7, visit_date: '2026-09-09', visit_time: '15:40', hospital, created_at: '2026-09-08T03:00:00Z', updated_at: null },
      { id: 72, user_id: 7, visit_date: '2026-09-12', visit_time: '22:40', hospital: '이후일정병원', created_at: '2026-09-08T03:00:00Z', updated_at: null },
    ];
    await page.route('**/api/v1/user/follow-up-visits**', (route) => route.fulfill({
      json: { items: visits, total: 2, offset: 0, limit: 100 },
    }));
    await page.goto('/dev/my-visits');
    const card = page.getByRole('region', { name: '다가오는 일정' }).getByRole('button');
    await expect(card).toContainText('9월 9일 수요일');
    await expect(card).toContainText('1일 남음');
    await expect(card).toContainText('15:40');
    expect((await card.innerText()).split(hospital)).toHaveLength(2);
    await expect(page.getByRole('region', { name: '이후 일정' }).getByRole('button')).toContainText('이후일정병원 · 22:40');
    expect(await card.evaluate((element) => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: testInfo.outputPath(`visit-card-${width}.png`), fullPage: true });
    await card.click();
    const editor = page.getByRole('dialog', { name: '진료일정 수정' });
    await expect(editor.getByLabel('병원')).toHaveValue(hospital);
    await expect(editor.getByLabel('진료일')).toHaveValue('2026-09-09');
    await expect(editor.getByRole('button', { name: '진료 시간 15:40' })).toBeVisible();
    await expect(editor.getByRole('button', { name: '삭제', exact: true })).toBeVisible();
  });
}
