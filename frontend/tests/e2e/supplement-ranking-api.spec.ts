import { expect, test, type Page, type Route } from 'playwright/test';

const useMock = process.env.VITE_USE_MOCK !== 'false';

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
    { supplement_nutrient_id: 1024, name: '오메가3', rank_no: 1 },
    { supplement_nutrient_id: 2048, name: '종합비타민', rank_no: 2 },
  ],
};

const PRODUCT_RESPONSE = {
  id: 2048,
  food_code: 'SUPPL-MULTI-2048',
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
  calcium_mg: '100.00',
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

async function loadRanking(page: Page): Promise<unknown> {
  return page.evaluate(async () => {
    const supplementApi = await import('/src/entities/supplement/api.ts');
    return supplementApi.getSupplementRanking();
  });
}

async function loadProduct(page: Page, productId: string): Promise<unknown> {
  return page.evaluate(async (requestedProductId) => {
    const supplementApi = await import('/src/entities/supplement/api.ts');
    return supplementApi.getSupplementProduct(requestedProductId);
  }, productId);
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

test('목업 랭킹은 화면용 타입과 서버가 정한 순위를 반환한다', async ({ page }) => {
  test.skip(!useMock, '목업 모드 계약입니다.');
  await page.goto('/dev/gallery');

  const ranking = await loadRanking(page);

  expect(ranking).toEqual({
    title: '9월 면역력 관리',
    items: [
      { rank: 1, productId: 'mock-501', name: '오메가3', alreadyRegistered: false },
      { rank: 2, productId: 'sp-003', name: '고려은단 멀티비타민 올인원', alreadyRegistered: false },
      { rank: 3, productId: 'sp-008', name: '오쏘몰 이뮨', alreadyRegistered: false },
      { rank: 4, productId: 'sp-009', name: '세노비스 트리플러스', alreadyRegistered: false },
      { rank: 5, productId: 'sp-015', name: '닥터린 멀티비타민 미네랄', alreadyRegistered: false },
    ],
  });
});

test('실 랭킹 API의 snake_case 응답을 화면용 타입으로 한 번만 매핑한다', async ({ page }) => {
  test.skip(useMock, '실 API 분기 계약입니다.');
  let requestedPath = '';
  await page.route('**/api/v1/display/med/nutr/rank', async (route) => {
    requestedPath = new URL(route.request().url()).pathname;
    await fulfillJson(route, RANKING_RESPONSE);
  });
  await page.goto('/dev/gallery');

  const ranking = await loadRanking(page);

  expect(requestedPath).toBe('/api/v1/display/med/nutr/rank');
  expect(ranking).toEqual({
    title: '9월 면역력 관리',
    items: [
      { rank: 1, productId: '1024', name: '오메가3', alreadyRegistered: false },
      { rank: 2, productId: '2048', name: '종합비타민', alreadyRegistered: false },
    ],
  });
});

test('실 랭킹 API의 404는 정상적인 null로 변환한다', async ({ page }) => {
  test.skip(useMock, '실 API 분기 계약입니다.');
  await page.route('**/api/v1/display/med/nutr/rank', async (route) => {
    await fulfillJson(
      route,
      { code: 'SUPPLEMENT_RANK_DISPLAY_NOT_FOUND', message: '현재 전시가 없습니다.' },
      404,
    );
  });
  await page.goto('/dev/gallery');

  await expect(loadRanking(page)).resolves.toBeNull();
});

test('실 랭킹 API의 404 외 오류는 숨기지 않고 호출자에게 전달한다', async ({ page }) => {
  test.skip(useMock, '실 API 분기 계약입니다.');
  await page.route('**/api/v1/display/med/nutr/rank', async (route) => {
    await fulfillJson(route, { code: 'SERVER_ERROR', message: '서버 오류' }, 500);
  });
  await page.goto('/dev/gallery');

  const result = await page.evaluate(async () => {
    const supplementApi = await import('/src/entities/supplement/api.ts');
    try {
      await supplementApi.getSupplementRanking();
      return { resolved: true, status: null };
    } catch (error) {
      return { resolved: false, status: Reflect.get(error as object, 'status') };
    }
  });

  expect(result).toEqual({ resolved: false, status: 500 });
});

test('제품 ID로 상세 API를 조회해 추가 시트용 제품으로 매핑한다', async ({ page }) => {
  test.skip(useMock, '실 API 분기 계약입니다.');
  let requestedPath = '';
  await page.route('**/api/v1/med/nutr/2048', async (route) => {
    requestedPath = new URL(route.request().url()).pathname;
    await fulfillJson(route, PRODUCT_RESPONSE);
  });
  await page.goto('/dev/gallery');

  const product = await loadProduct(page, '2048');

  expect(requestedPath).toBe('/api/v1/med/nutr/2048');
  expect(product).toMatchObject({
    productId: '2048',
    productName: '종합비타민',
    servingDescription: '2정',
    servingSize: '1000mg',
    dailyFrequency: '1회',
    recommendedDoseAmount: 2,
    doseUnit: '정',
    recommendedSlots: ['morning'],
  });
});
