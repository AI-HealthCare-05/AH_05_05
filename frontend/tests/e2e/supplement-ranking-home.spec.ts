import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const RANKING_RESPONSE = {
  display_id: 3,
  title: '9월 면역력 관리',
  start_at: '2026-08-01T00:00:00+09:00',
  end_at: '2026-09-30T23:59:59+09:00',
  is_enabled: true,
  created_by_admin_id: 1,
  created_at: '2026-08-27T17:35:52+09:00',
  updated_at: null,
  items: [
    { supplement_nutrient_id: 701, name: '튼튼 철분 캡슐', rank_no: 1 },
    { supplement_nutrient_id: 702, name: '종합비타민', rank_no: 2 },
  ],
};

const PRODUCT_RESPONSE = {
  id: 702,
  food_code: 'SUPPL-MULTI-702',
  name: '종합비타민',
  basis_qty: '1000mg',
  energy_kcal: 0,
  water_g: null,
  protein_g: null,
  fat_g: null,
  ash_g: null,
  carb_g: null,
  sugar_g: null,
  fiber_g: null,
  calcium_mg: null,
  iron_mg: null,
  phosphorus_mg: null,
  potassium_mg: null,
  sodium_mg: null,
  vitamin_a_ug_rae: null,
  retinol_ug: null,
  beta_carotene_ug: null,
  thiamine_mg: null,
  riboflavin_mg: null,
  niacin_mg: null,
  vitamin_c_mg: null,
  vitamin_d_ug: '10.00',
  cholesterol_mg: null,
  sat_fat_g: null,
  trans_fat_g: null,
  serving_desc: '2정',
  serving_size: '1000mg',
  daily_freq: '1회',
  target: '성인',
};

const REGISTERED_PRODUCT = {
  ...PRODUCT_RESPONSE,
  id: 701,
  food_code: 'SUPPL-IRON-701',
  name: '튼튼 철분 캡슐',
};

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'e2e-ranking-token');
    window.sessionStorage.setItem('poke.account-principal', 'ranking-e2e@example.com');
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function routeCommon(
  page: Page,
  options?: { supplementStatus?: number; supplementGate?: Promise<void> },
) {
  await page.route('**/api/v1/display/med/nutr/rank', async (route) => {
    await fulfillJson(route, RANKING_RESPONSE);
  });
  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    await options?.supplementGate;
    if (options?.supplementStatus) {
      await fulfillJson(route, { code: 'SERVER_ERROR', message: '목록 오류' }, options.supplementStatus);
      return;
    }
    await fulfillJson(route, {
      items: [
        {
          id: 9001,
          dose_amount: '1.000',
          dose_unit: '정',
          start_date: '2026-08-27',
          end_date: null,
          status: 'ACTIVE',
          note: null,
          created_at: '2026-08-27T09:00:00+09:00',
          updated_at: null,
          slots: [{ slot: 'MORNING', time: '08:00:00' }],
          supplement: REGISTERED_PRODUCT,
        },
      ],
      total: 1,
      offset: 0,
      limit: 100,
    });
  });
  await page.route('**/api/v1/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      phoneNumber: '01012345678',
      birthDate: '1990-01-01',
      gender: 'female',
    });
  });
}

test('등록 목록을 확인하는 동안 랭킹 행을 추가 버튼으로 노출하지 않는다', async ({ page }) => {
  await authenticate(page);
  let releaseSupplements = () => {};
  const supplementGate = new Promise<void>((resolve) => {
    releaseSupplements = resolve;
  });
  await routeCommon(page, { supplementGate });
  await page.goto('/dev/home-empty');

  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking.getByText('튼튼 철분 캡슐', { exact: true })).toBeVisible();
  await expect(ranking.getByRole('button', { name: /1위 튼튼 철분 캡슐/ })).toHaveCount(0);

  releaseSupplements();
  await expect(ranking.getByText('등록됨', { exact: true })).toBeVisible();
  await expect(ranking.getByRole('button', { name: /1위 튼튼 철분 캡슐/ })).toHaveCount(0);
});

test('홈은 서버 제목과 고정 부제만 표시하고 등록 여부를 제품 ID로 판정한다', async ({ page }) => {
  await authenticate(page);
  await routeCommon(page);
  await page.goto('/dev/home-empty');

  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking.getByRole('heading', { name: '9월 면역력 관리' })).toBeVisible();
  await expect(ranking.getByText('RxVita가 골랐어요', { exact: true })).toBeVisible();
  await expect(ranking.getByText('튼튼 철분 캡슐', { exact: true })).toBeVisible();
  await expect(ranking.getByText('등록됨', { exact: true })).toBeVisible();
  await expect(ranking).not.toContainText(/인기|많이|베스트|추천|명이 등록|전시 기간/);

  const rows = ranking.getByRole('listitem');
  await expect(rows).toHaveCount(2);
  for (let index = 0; index < 2; index += 1) {
    expect((await rows.nth(index).boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
});

test('등록 목록 조회가 실패해도 랭킹은 배지 없이 표시한다', async ({ page }) => {
  await authenticate(page);
  await routeCommon(page, { supplementStatus: 500 });
  await page.goto('/dev/home-empty');

  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking.getByRole('heading', { name: '9월 면역력 관리' })).toBeVisible();
  await expect(ranking.getByText('등록됨', { exact: true })).toHaveCount(0);
  await expect(page.getByText('오늘의 복약', { exact: true })).toBeVisible();
});

test('랭킹 404와 빈 items는 카드만 숨기고 오늘의 복약은 유지한다', async ({ page }) => {
  await authenticate(page);
  await routeCommon(page);
  await page.unroute('**/api/v1/display/med/nutr/rank');
  await page.route('**/api/v1/display/med/nutr/rank', async (route) => {
    await fulfillJson(
      route,
      { code: 'SUPPLEMENT_RANK_DISPLAY_NOT_FOUND', message: '현재 전시가 없습니다.' },
      404,
    );
  });
  await page.goto('/dev/home-empty');

  await expect(page.getByRole('region', { name: '영양제 랭킹' })).toHaveCount(0);
  await expect(page.getByText('오늘의 복약', { exact: true })).toBeVisible();

  await page.unroute('**/api/v1/display/med/nutr/rank');
  await page.route('**/api/v1/display/med/nutr/rank', async (route) => {
    await fulfillJson(route, { ...RANKING_RESPONSE, items: [] });
  });
  await page.reload();

  await expect(page.getByRole('region', { name: '영양제 랭킹' })).toHaveCount(0);
  await expect(page.getByText('오늘의 복약', { exact: true })).toBeVisible();
});

test('미등록 랭킹 행은 검색 없이 상세 API로 제품을 채운 추가 시트를 연다', async ({ page }) => {
  await authenticate(page);
  await routeCommon(page);
  let detailPath = '';
  let searchRequestCount = 0;
  await page.route('**/api/v1/med/nutr/702', async (route) => {
    detailPath = new URL(route.request().url()).pathname;
    await fulfillJson(route, PRODUCT_RESPONSE);
  });
  await page.route('**/api/v1/med/nutr?**', async (route) => {
    searchRequestCount += 1;
    await fulfillJson(route, { items: [], total: 0, offset: 0, limit: 20 });
  });
  await page.goto('/dev/home-empty');

  await page
    .getByRole('region', { name: '영양제 랭킹' })
    .getByRole('button', { name: /2위 종합비타민/ })
    .click();

  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('종합비타민', { exact: true })).toBeVisible();
  await expect(sheet.getByText('2 정', { exact: true })).toBeVisible();
  expect(detailPath).toBe('/api/v1/med/nutr/702');
  expect(searchRequestCount).toBe(0);
});
