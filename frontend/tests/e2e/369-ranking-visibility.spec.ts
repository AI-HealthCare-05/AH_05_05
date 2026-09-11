import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const RANKING = {
  display_id: 369,
  title: '현재 전시 랭킹',
  start_at: '2026-09-01T00:00:00+09:00',
  end_at: '2026-09-30T23:59:59+09:00',
  is_enabled: true,
  created_by_admin_id: 1,
  created_at: '2026-09-01T00:00:00+09:00',
  updated_at: null,
  items: [{ supplement_nutrient_id: 36901, name: '전시 비타민', rank_no: 1 }],
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function prepare(page: Page, authenticated: boolean) {
  if (authenticated) {
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', '369-ranking-token');
      sessionStorage.setItem('poke.account-principal', '369-ranking@example.com');
    });
  }
  // Keep unrelated backend reads local; ranking and search use their actual adapters.
  await page.route('**/api/v1/**', route => json(route, { items: [], total: 0, offset: 0, limit: 100 }));
  await page.route('**/api/v1/users/me', route => json(route, {
    name: '테스트', phoneNumber: '01012345678', birthDate: '1990-01-01', gender: 'female',
  }));
}

test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));

const surfaces = [
  { name: '둘러보기', path: '/supplements?tab=browse', authenticated: true },
  { name: '로그인 홈', path: '/dev/home-empty', authenticated: true },
  { name: '비로그인 홈', path: '/home', authenticated: false },
];

for (const surface of surfaces) {
  for (const unavailable of [
    // The current-display endpoint returns the same 404 for absent, expired and disabled displays.
    { name: '미등록 또는 기간 종료', status: 404, body: { code: 'SUPPLEMENT_RANK_DISPLAY_NOT_FOUND', message: '현재 전시가 없습니다.' } },
    { name: '제목만 등록', status: 200, body: { ...RANKING, items: [] } },
    { name: '조회 실패', status: 500, body: { code: 'SERVER_ERROR', message: '랭킹 조회 실패' } },
  ]) {
    test(`${surface.name}: ${unavailable.name} 랭킹 영역과 안내 문구를 숨긴다`, async ({ page }) => {
      await prepare(page, surface.authenticated);
      await page.route('**/api/v1/display/med/nutr/rank', route => json(route, unavailable.body, unavailable.status));
      const response = page.waitForResponse('**/api/v1/display/med/nutr/rank');
      await page.goto(surface.path);
      await response;
      await page.waitForLoadState('networkidle');

      await expect(page.getByRole('region', { name: '영양제 랭킹' })).toHaveCount(0);
      await expect(page.getByText(/랭킹을 불러오는 중|랭킹을 불러오지 못|현재 공개된 영양제 랭킹|랭킹 조회 실패/)).toHaveCount(0);
      if (surface.authenticated && surface.name === '둘러보기') {
        await expect(page.getByRole('searchbox', { name: '영양제 제품 검색' })).toBeVisible();
        await page.getByRole('searchbox').fill('없는 제품');
        await expect(page.getByText('검색 결과가 없어요.', { exact: true })).toBeVisible();
      } else if (surface.authenticated) {
        await expect(page.getByRole('tabpanel', { name: '오늘의 복약', exact: true })).toBeVisible();
      } else {
        await expect(page.getByRole('heading', { name: '오늘의 복약', exact: true })).toBeVisible();
      }
    });
  }

  test(`${surface.name}: 응답 대기 중 영역을 숨기고 현재 제품이 도착하면 표시한다`, async ({ page }) => {
    await prepare(page, surface.authenticated);
    let release = () => {};
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v1/display/med/nutr/rank', async route => {
      await gate;
      await json(route, RANKING);
    });
    const request = page.waitForRequest('**/api/v1/display/med/nutr/rank');
    await page.goto(surface.path);
    await request;
    try {
      await expect(page.getByRole('region', { name: '영양제 랭킹' })).toHaveCount(0);
      await expect(page.getByText(/랭킹을 불러오는 중|랭킹을 불러오지 못/)).toHaveCount(0);
    } finally {
      release();
    }
    const ranking = page.getByRole('region', { name: '영양제 랭킹' });
    await expect(ranking.getByRole('heading', { name: RANKING.title })).toBeVisible();
    await expect(ranking.getByRole('button', { name: '1위 전시 비타민 제품 정보' })).toBeEnabled();
    await expect(ranking.getByRole('listitem')).toHaveCount(1);
  });
}
