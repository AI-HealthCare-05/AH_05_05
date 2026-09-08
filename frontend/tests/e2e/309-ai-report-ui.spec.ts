import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => test.skip(IS_REAL_API, MOCK_ONLY_REASON));
// WSL's mounted checkout can need more than the global 10s for Vite's first transform.
test.setTimeout(30_000);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'e2e-report-token');
    sessionStorage.setItem('poke.account-principal', 'report-preview@example.com');
  });
});

for (const source of ['medications', 'supplements'] as const) {
  test(`${source}: report entry is explicit and sends no report/chat request`, async ({ page }) => {
    const reportRequests: string[] = [];
    page.on('request', (request) => {
      if (/\/v1\/(chat|reports)/.test(request.url())) {
        reportRequests.push(`${request.method()} ${request.url()}`);
      }
    });
    await page.goto(`/${source}`);
    await expect(page.getByRole('button', { name: source === 'medications' ? '처방 관리' : '영양제 관리' })).toBeVisible();
    await page.getByRole('banner').getByRole('button', { name: 'AI 보고서 받기' }).click();
    await expect(page).toHaveURL(new RegExp(`/reports/new\\?source=${source}$`));
    await expect(page.getByRole('heading', { name: '보고서 기능을 준비하고 있어요' })).toBeVisible();
    await expect(page.getByText('아직 보고서를 생성하거나 건강정보를 전송하지 않아요.')).toBeVisible();
    await expect(page.getByRole('button', { name: '보고서 생성 준비 중' })).toBeDisabled();
    await page.getByRole('button', { name: 'AI 보고서 모아보기' }).click();
    await expect(page).toHaveURL('/reports');
    await expect(page.getByRole('heading', { name: '아직 받은 AI 보고서가 없어요' })).toBeVisible();
    expect(reportRequests).toEqual([]);
  });
}

test('My has report collection entry, with a working return path', async ({ page }) => {
  await page.goto('/my');
  await page.getByRole('button', { name: 'AI 보고서 모아보기' }).click();
  await expect(page).toHaveURL('/reports');
  await page.getByRole('button', { name: '마이페이지로 돌아가기' }).click();
  await expect(page).toHaveURL('/my');
});

test('direct report URLs remain protected for guests', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  for (const path of ['/reports', '/reports/new?source=medications']) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('heading', { name: 'AI 보고서' })).toHaveCount(0);
  }
  await context.close();
});

test('body management remains available and report UI fits a narrow screen', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto('/medications');
  await page.getByRole('button', { name: '처방 관리' }).click();
  await expect(page.getByRole('heading', { name: '삭제할 처방을 선택하세요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '선택한 처방 삭제' })).toBeDisabled();
  await page.getByRole('button', { name: '관리 완료' }).click();
  await page.getByRole('button', { name: 'AI 보고서 받기' }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('medication-report-320.png'), fullPage: true });
  await page.goto('/supplements');
  await page.getByRole('button', { name: '영양제 관리' }).click();
  await expect(page.getByRole('button', { name: '관리 완료' })).toBeVisible();
  await page.getByRole('button', { name: '관리 완료' }).click();
  await page.screenshot({ path: testInfo.outputPath('supplement-report-entry-320.png'), fullPage: true });
  await page.goto('/reports');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('report-collection-320.png'), fullPage: true });
});
