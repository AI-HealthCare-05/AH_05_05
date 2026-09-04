import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'e2e-medication-empty-token');
    window.sessionStorage.setItem('poke.account-principal', 'medication-empty-e2e@example.com');
  });
}

async function fulfillJson(route: Route, body: unknown, status: number) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

test('404 복약 목록은 홈과 복용약 탭에서 등록 CTA를 제공한다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, { detail: 'Not Found' }, 404),
  );

  await page.goto('/home');

  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
  await expect(
    page.getByText('복약정보를 등록하시면 시간에 맞춰 알림을 받으실 수 있어요.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toHaveCount(0);
  await page.getByRole('button', { name: '약봉투 등록하기', exact: true }).click();
  await expect(page).toHaveURL('/document-upload');

  await page.goto('/medications');

  await expect(page.getByText('복용약을 등록해 주세요.', { exact: true })).toBeVisible();
  await expect(page.getByText('복용약을 불러오지 못했어요')).toHaveCount(0);
  await page.getByRole('button', { name: '약봉투 등록하기', exact: true }).click();
  await expect(page).toHaveURL('/document-upload');
});

test('500 복약 목록은 홈과 복용약 탭의 오류 카드로 남는다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, { message: '복약 서비스 오류' }, 500),
  );

  await page.goto('/home');
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toBeVisible();
  await expect(page.getByText('복약 서비스 오류')).toBeVisible();

  await page.goto('/medications');
  await expect(page.getByText('복용약을 불러오지 못했어요')).toBeVisible();
  await expect(page.getByText('복약 서비스 오류')).toBeVisible();
});
