import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.skip(IS_REAL_API, MOCK_ONLY_REASON);
test.setTimeout(60_000);
test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T03:00:00Z'));
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.route('**/api/v1/**', route => route.fulfill({ json: { items: [], total_count: 0, totalCount: 0 } }));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'report-back-test');
    sessionStorage.setItem('poke.account-principal', 'report-back@example.invalid');
  });
});

for (const source of ['medications', 'supplements']) {
  const label = source === 'medications' ? '복약' : '영양제';
  for (const exit of ['header', 'footer', 'browser', 'reload']) {
    test(`${source}: ${exit} 복귀 후 뒤로가기는 보고서로 순환하지 않고 홈에 도착한다`, async ({ page }) => {
      const requests: string[] = [];
      page.on('request', request => {
        if (request.method() === 'POST' && /\/api\/v1\/(reports|intake-reports|chat)/.test(request.url())) requests.push(request.url());
      });
      await page.goto('/home');
      await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: label, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/${source}$`));
      await page.getByRole('button', { name: 'AI 보고서 받기', exact: true }).click();
      await expect(page.getByRole('button', { name: '보고서 생성하기', exact: true })).toBeVisible();
      if (exit === 'reload') await page.reload();
      if (exit === 'browser') await page.goBack();
      else if (exit === 'footer') await page.getByRole('button', { name: source === 'medications' ? '복약으로 돌아가기' : '영양제로 돌아가기', exact: true }).click();
      else await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/${source}$`));
      await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
      await expect(page).toHaveURL(/\/home$/);
      expect(requests).toEqual([]);
    });
  }

  test(`${source}: 보고서 직접 진입에서도 원래 탭을 거쳐 홈으로 복귀한다`, async ({ page }) => {
    await page.goto(`/reports/new?source=${source}`);
    await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/${source}$`));
    await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
    await expect(page).toHaveURL(/\/home$/);
  });
}
