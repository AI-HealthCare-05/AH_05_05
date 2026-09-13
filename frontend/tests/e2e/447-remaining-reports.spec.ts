import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';
import {
  remainingBaseReport,
  remainingEmptyReport,
  remainingV11Report,
} from './helpers/447-remaining-report-fixtures';

const SCREENSHOT_DIR = '/mnt/c/dev/AH_05_05/design-plans/447-implementation/screenshots';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(120_000);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '447-remaining-reports');
    sessionStorage.setItem('poke.account-principal', '447-remaining-reports@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
  await page.route('**/api/v1/**', (route) => route.fulfill({ status: 503, json: { message: '447 remaining reports: unhandled API blocked' } }));
});

async function expectReadingMain(page: Page, viewportWidth: number) {
  const geometry = await page.locator('main').evaluate((main) => {
    const rect = main.getBoundingClientRect();
    return {
      left: rect.left,
      right: rect.right,
      width: rect.width,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
    };
  });
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.width).toBeLessThanOrEqual(760);
  if (viewportWidth <= 760) expect(geometry.width).toBe(viewportWidth);
  expect(Math.abs(geometry.left - (viewportWidth - geometry.right))).toBeLessThanOrEqual(1);
}

for (const source of ['medications', 'supplements'] as const) {
  for (const width of [320, 390]) {
    test(`${source} ${width}px pending/error/default/v11/empty는 좁은 읽기 폭과 상태 의미를 유지한다`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });

      await page.route('**/api/v1/intake-reports', () => {});
      await page.goto(`/reports/new?source=${source}`);
      await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
      await expect(page.getByRole('status')).toContainText('보고서 생성 중');
      await expectReadingMain(page, width);

      await page.unroute('**/api/v1/intake-reports');
      await page.route('**/api/v1/intake-reports', (route) => route.fulfill({ status: 503, json: { code: 'REPORT_UNAVAILABLE', message: '보고서를 생성하지 못했어요.' } }));
      await page.goto(`/reports/new?source=${source}`);
      await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
      await expect(page.getByRole('alert')).toContainText('보고서를 생성하지 못했어요.');
      await expectReadingMain(page, width);

      for (const [state, report] of [
        ['default', remainingBaseReport],
        ['v11', remainingV11Report],
        ['empty', remainingEmptyReport],
      ] as const) {
        await page.unroute('**/api/v1/intake-reports');
        await page.route('**/api/v1/intake-reports', (route) => route.fulfill({ json: report }));
        await page.goto(`/reports/new?source=${source}`);
        await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
        if (state === 'default') await expect(page.getByRole('heading', { name: '복용 정보 요약' })).toBeVisible();
        if (state === 'v11') await expect(page.locator('.v11-report')).toBeVisible();
        if (state === 'empty') await expect(page.getByRole('heading', { name: '분석할 복용 정보가 없어요' })).toBeVisible();
        await expectReadingMain(page, width);
      }
    });
  }
}

for (const [state, report] of [
  ['default', remainingBaseReport],
  ['v11', remainingV11Report],
] as const) {
  test(`desktop ${state} 보고서의 main과 CTA는 760px 읽기 열에 함께 묶인다`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.route('**/api/v1/intake-reports', (route) => route.fulfill({ json: report }));
    await page.goto('/reports/new?source=medications');
    await page.getByRole('button', { name: '보고서 생성하기', exact: true }).click();
    if (state === 'default') await expect(page.getByRole('heading', { name: '복용 정보 요약' })).toBeVisible();
    else await expect(page.locator('.v11-report')).toBeVisible();
    await expectReadingMain(page, 1280);
    const main = page.locator('main');
    const email = page.getByRole('button', { name: '이메일로 받기', exact: true });
    const [mainBox, emailBox] = await Promise.all([main.boundingBox(), email.boundingBox()]);
    expect(mainBox).not.toBeNull();
    expect(emailBox).not.toBeNull();
    expect(emailBox!.x).toBeGreaterThanOrEqual(mainBox!.x);
    expect(emailBox!.x + emailBox!.width).toBeLessThanOrEqual(mainBox!.x + mainBox!.width);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/task-6-report-${state}-1280.png`, fullPage: true });
  });
}
