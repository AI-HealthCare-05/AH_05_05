import { expect, test } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.use({ timezoneId: 'UTC' });

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-08T03:00:00Z'));
  // Exercise the real HTTP client while preventing all backend/database access.
  await page.route('**/api/v1/**', (route) => route.abort());
});

test('등록과 수정은 빈 병원을 막고 정리한 병원명과 선택 시간을 API로 보낸다', async ({ page }) => {
  const writes: { method: string; body: unknown }[] = [];
  const storedVisit = {
    id: 53,
    user_id: 7,
    visit_date: '2026-09-20',
    visit_time: null,
    hospital: '내과',
    created_at: '2026-09-08T12:00:00+09:00',
    updated_at: null,
  };
  await page.route('**/api/v1/user/follow-up-visits**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100 } });
      return;
    }
    writes.push({ method: request.method(), body: request.postDataJSON() });
    await route.fulfill({
      status: request.method() === 'POST' ? 201 : 200,
      json: request.method() === 'POST'
        ? storedVisit
        : { ...storedVisit, hospital: '○○이비인후과', updated_at: '2026-09-08T12:01:00+09:00' },
    });
  });

  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: '진료일정 추가' }).click();
  const createSheet = page.getByRole('dialog', { name: '진료일정 추가' });
  await createSheet.getByLabel('진료일').fill('2026-09-20');
  await expect(createSheet.getByRole('button', { name: '저장' })).toBeDisabled();
  await createSheet.getByLabel('병원').fill(' \u3000 ');
  await expect(createSheet.getByRole('button', { name: '저장' })).toBeDisabled();
  expect(writes).toEqual([]);
  await createSheet.getByLabel('병원').fill('  내과  ');
  await createSheet.getByRole('button', { name: '저장' }).click();
  const created = page.getByRole('button', { name: /9월 20일.*내과.*시간 미정/ });
  await expect(created).toBeVisible();
  expect(writes).toEqual([{
    method: 'POST',
    body: { visit_date: '2026-09-20', visit_time: null, hospital: '내과' },
  }]);

  await created.click();
  const editSheet = page.getByRole('dialog', { name: '진료일정 수정' });
  await editSheet.getByLabel('병원').fill('');
  await expect(editSheet.getByRole('button', { name: '저장' })).toBeDisabled();
  await editSheet.getByLabel('병원').fill(' \u3000 ');
  await expect(editSheet.getByRole('button', { name: '저장' })).toBeDisabled();
  expect(writes).toHaveLength(1);
  await editSheet.getByLabel('병원').fill('  ○○이비인후과  ');
  await editSheet.getByRole('button', { name: '저장' }).click();
  await expect(page.getByRole('button', { name: /9월 20일.*○○이비인후과.*시간 미정/ })).toBeVisible();
  expect(writes).toEqual([
    { method: 'POST', body: { visit_date: '2026-09-20', visit_time: null, hospital: '내과' } },
    { method: 'PATCH', body: { visit_date: '2026-09-20', visit_time: null, hospital: '○○이비인후과' } },
  ]);
});
