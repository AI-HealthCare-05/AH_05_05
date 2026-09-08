import { expect, test } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => test.skip(IS_REAL_API, MOCK_ONLY_REASON));
// WSL's mounted checkout can need more than the global 10s for Vite's first transform.
test.setTimeout(120_000);

test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'e2e-report-token');
    sessionStorage.setItem('poke.account-principal', 'report-preview@example.com');
  });
});

for (const source of ['medications', 'supplements'] as const) {
  test(`${source}: report entry is explicit and sends no report/chat request`, async ({ page }) => {
    const reportRequests: string[] = [];
    page.on('request', (request) => {
      if (/\/v1\/(chat|reports|intake-reports)/.test(request.url())) {
        reportRequests.push(`${request.method()} ${request.url()}`);
      }
    });
    await page.goto(`/${source}`);
    await expect(page.getByRole('button', { name: '삭제', exact: true })).toBeVisible();
    await page.getByRole('banner').getByRole('button', { name: 'AI 보고서 받기' }).click();
    await expect(page).toHaveURL(new RegExp(`/reports/new\\?source=${source}$`));
    await expect(page.getByRole('heading', { name: '현재 복용 정보를 함께 살펴봐요' })).toBeVisible();
    await expect(page.getByText('보고서는 저장되지 않아요.', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '보고서 생성하기', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: source === 'medications' ? '복약으로 돌아가기' : '영양제로 돌아가기' }).click();
    await expect(page).toHaveURL(`/${source}`);
    expect(reportRequests).toEqual([]);
  });
}

test('My has report entry, with a working return path', async ({ page }) => {
  await page.goto('/my');
  await page.getByRole('button', { name: 'AI 보고서', exact: true }).click();
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
  await expect(page.getByRole('button', { name: '삭제', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('heading', { name: '삭제할 처방을 선택하세요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '선택한 처방 삭제' })).toBeDisabled();
  await page.getByRole('button', { name: '관리 완료' }).click();
  await page.getByRole('button', { name: 'AI 보고서 받기' }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('medication-report-320.png'), fullPage: true });
  await page.goto('/supplements');
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('button', { name: '관리 완료' })).toBeVisible();
  await page.getByRole('button', { name: '관리 완료' }).click();
  await page.screenshot({ path: testInfo.outputPath('supplement-report-entry-320.png'), fullPage: true });
  await page.goto('/reports');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('report-collection-320.png'), fullPage: true });
});

test('supplement add opens directly while delete only opens selection', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto('/supplements');
  const listHeader = page.getByRole('heading', { name: /먹고 있는 영양제/ }).locator('..');
  await expect(listHeader.getByRole('button', { name: '영양제 추가', exact: true })).toBeVisible();
  await listHeader.getByRole('button', { name: '영양제 추가', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '영양제 추가', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('checkbox').first()).toBeVisible();
  await expect(page.getByRole('button', { name: '선택한 0개 삭제', exact: true })).toBeDisabled();
  await page.getByRole('checkbox').first().check();
  await expect(page.getByRole('button', { name: '선택한 1개 삭제', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '관리 완료', exact: true }).click();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('supplement-add-delete-320.png'), fullPage: true });
});
