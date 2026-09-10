import path from 'node:path';
import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

const PUBLIC_RANKING = {
  display_id: 384,
  title: '백오피스 공개 랭킹',
  start_at: '2026-09-01T00:00:00+09:00',
  end_at: '2026-09-30T23:59:59+09:00',
  is_enabled: true,
  created_by_admin_id: 1,
  created_at: '2026-09-01T00:00:00+09:00',
  updated_at: null,
  items: [
    { supplement_nutrient_id: 38401, name: '백오피스 비타민', rank_no: 1 },
    { supplement_nutrient_id: 38402, name: '백오피스 오메가3', rank_no: 2 },
  ],
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function routePublicRanking(page: Page, body: unknown, status = 200) {
  let requests = 0;
  let authorizationHeader: string | undefined;
  await page.route('**/api/v1/display/med/nutr/rank', async (route) => {
    requests += 1;
    authorizationHeader = route.request().headers().authorization;
    await fulfillJson(route, body, status);
  });
  return {
    requests: () => requests,
    authorizationHeader: () => authorizationHeader,
  };
}

test.beforeEach(() => {
  test.setTimeout(30_000);
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('비로그인 홈은 목업 랭킹 대신 백오피스 공개 랭킹 API 응답을 표시한다', async ({ page }, testInfo) => {
  const request = await routePublicRanking(page, PUBLIC_RANKING);

  await page.goto('/home');

  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking).toBeVisible();
  await captureComparison(page, testInfo, 'issue5-public-ranking.png');
  await expect(ranking.getByRole('heading', { name: '백오피스 공개 랭킹' })).toBeVisible();
  await expect(ranking.getByText('백오피스 비타민', { exact: true })).toBeVisible();
  await expect(ranking.getByText('오쏘몰 이뮨', { exact: true })).toHaveCount(0);
  await expect(ranking.getByRole('listitem')).toHaveCount(2);
  expect(request.requests()).toBeGreaterThan(0);
  expect(request.authorizationHeader()).toBeUndefined();
});

test('백오피스에 현재 공개 랭킹이 없으면 예시 제품 대신 정확한 빈 상태를 표시한다', async ({ page }, testInfo) => {
  await routePublicRanking(
    page,
    { code: 'SUPPLEMENT_RANK_DISPLAY_NOT_FOUND', message: '현재 전시가 없습니다.' },
    404,
  );

  await page.goto('/home');

  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking).toBeVisible();
  await captureComparison(page, testInfo, 'issue5-ranking-empty.png');
  await expect(ranking.getByText('현재 공개된 영양제 랭킹이 없어요.', { exact: true })).toBeVisible();
  await expect(ranking.getByRole('listitem')).toHaveCount(0);
  await expect(ranking.getByText('오쏘몰 이뮨', { exact: true })).toHaveCount(0);
});

test('백오피스 공개 랭킹의 items가 비어 있어도 같은 빈 상태를 표시한다', async ({ page }) => {
  await routePublicRanking(page, { ...PUBLIC_RANKING, items: [] });

  await page.goto('/home');

  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking.getByText('현재 공개된 영양제 랭킹이 없어요.', { exact: true })).toBeVisible();
  await expect(ranking.getByRole('listitem')).toHaveCount(0);
});

async function captureComparison(
  page: Page,
  testInfo: { config: { rootDir: string } },
  filename: string,
) {
  const variant = process.env.CAPTURE_384_VARIANT;
  if (variant !== 'before' && variant !== 'after') return;
  await page.locator('main').evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.screenshot({
    path: path.resolve(testInfo.config.rootDir, '../../../design-plans/384/screenshots', variant, filename),
    fullPage: true,
  });
}
