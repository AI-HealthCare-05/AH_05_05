import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

async function authenticate(page: Page) {
  // Home also loads challenge summaries; unmocked requests would reject the fake
  // token and turn this authenticated empty-state test into a guest-page test.
  await page.route('**/api/v1/user/challenges', route => fulfillJson(route, { items: [], total_count: 0 }, 200));
  await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, { items: [], totalCount: 0 }, 200));
  await page.route('**/api/v1/display/med/nutr/rank', route => fulfillJson(route, null, 200));
  await page.route('**/api/v1/medications/doses?**', route => fulfillJson(route, [], 200));
  await page.route('**/api/v1/med/user-suppl-nutr?**', (route) =>
    fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 }, 200),
  );
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
  await page.route('**/api/v1/medications/exists', route => fulfillJson(route, false, 200));

  await page.goto('/home');

  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
  await expect(
    page.getByText('복약정보를 등록하시면 시간에 맞춰 알림을 받으실 수 있어요.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toHaveCount(0);
  await page.getByRole('button', { name: '약봉투 등록하기', exact: true }).click();
  await expect(page).toHaveURL('/document-upload');

  await page.goto('/medications');

  await expect(page.getByText('복용약을 등록하고 관리하기', { exact: true })).toBeVisible();
  await expect(page.getByText('복용약을 불러오지 못했어요')).toHaveCount(0);
  await page.getByRole('button', { name: '복용약 등록하기', exact: true }).click();
  await expect(page).toHaveURL('/document-upload');
});

for (const hasHistory of [false, true]) {
  test(`빈 목록은 전체 처방 이력 ${hasHistory ? '있음' : '없음'}에 맞게 안내한다`, async ({ page }, testInfo) => {
    await authenticate(page);
    await page.route('**/api/v1/medications', route => fulfillJson(route, [], 200));
    await page.route('**/api/v1/medications/exists', route => fulfillJson(route, hasHistory, 200));
    await page.goto('/medications');
    await expect(page.getByRole('heading', {
      name: hasHistory ? '현재 먹고 있는 약이 없어요' : '복용약을 등록하고 관리하기',
    })).toBeVisible();
    await expect(page.getByRole('button', { name: '처방 추가', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '선택', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '최근 6개월' })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`empty-history-${hasHistory}.png`) });
    await page.getByRole('button', { name: '복용약 등록하기', exact: true }).click();
    await expect(page).toHaveURL('/document-upload');
  });
}

test('처방 존재 확인 실패를 신규 사용자로 오인하지 않고 재시도한다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/medications', route => fulfillJson(route, [], 200));
  await page.route('**/api/v1/medications/exists', route => fulfillJson(route, { message: '처방 확인 오류' }, 500));
  await page.goto('/medications');
  await expect(page.getByText('복용약을 불러오지 못했어요')).toBeVisible();
  await expect(page.getByText('복용약을 등록하고 관리하기')).toHaveCount(0);
  await page.route('**/api/v1/medications/exists', route => fulfillJson(route, true, 200));
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page.getByRole('heading', { name: '현재 먹고 있는 약이 없어요' })).toBeVisible();
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
