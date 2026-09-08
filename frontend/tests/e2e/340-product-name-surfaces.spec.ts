import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const RANKING_NAME = `맞춤영양랭킹${'RANKINGSUPPLEMENT'.repeat(12)}캡슐`;
const PRODUCT_NAME = `초고함량복합영양제${'PRODUCTSUPPLEMENT'.repeat(12)}정`;

function product(id: number, name: string) {
  return {
    id,
    food_code: `SUPPL-${id}`,
    name,
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
    rating_average: 4.5,
    review_count: 12,
  };
}

const RANKING_PRODUCT = product(2049, RANKING_NAME);
const SEARCH_PRODUCT = product(2048, PRODUCT_NAME);

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function expectContained(locator: Locator, container: Locator) {
  await expect(locator).toBeVisible();
  const metrics = await locator.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      scrollFits: element.scrollWidth <= element.clientWidth + 1,
      heightFits: element.scrollHeight <= element.clientHeight + 1,
      textOverflow: getComputedStyle(element).textOverflow,
      left: rect.left,
      right: rect.right,
    };
  });
  const boundary = await container.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, scrollFits: element.scrollWidth <= element.clientWidth + 1 };
  });
  expect(metrics.textOverflow).not.toBe('ellipsis');
  expect(metrics.scrollFits).toBe(true);
  expect(metrics.heightFits).toBe(true);
  expect(metrics.left).toBeGreaterThanOrEqual(boundary.left - 1);
  expect(metrics.right).toBeLessThanOrEqual(boundary.right + 1);
  expect(boundary.scrollFits).toBe(true);
}

async function routeProducts(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'long-product-name-test');
    sessionStorage.setItem('poke.account-principal', 'long-product-name@example.com');
  });
  await page.route('**/api/v1/display/med/nutr/rank', (route) => fulfillJson(route, {
    display_id: 3,
    title: '긴 이름 추천',
    start_at: '2026-09-01T00:00:00+09:00',
    end_at: '2026-09-30T23:59:59+09:00',
    is_enabled: true,
    created_by_admin_id: 1,
    created_at: '2026-09-01T00:00:00+09:00',
    updated_at: null,
    items: [{ supplement_nutrient_id: 2049, name: RANKING_NAME, rank_no: 1 }],
  }));
  await page.route('**/api/v1/med/user-suppl-nutr**', (route) => fulfillJson(route, {
    items: [{
      id: 9001,
      dose_amount: '1.000',
      dose_unit: '정',
      start_date: '2026-09-01',
      end_date: null,
      status: 'ACTIVE',
      score: null,
      note: null,
      review_body: null,
      created_at: '2026-09-01T09:00:00+09:00',
      updated_at: null,
      slots: [{ slot: 'MORNING', time: '08:00:00' }],
      supplement: RANKING_PRODUCT,
    }],
    total: 1,
    offset: 0,
    limit: 100,
    nutrient_standard: null,
  }));
  await page.route('**/api/v1/med/nutr/2048/reviews?*', (route) => fulfillJson(route, {
    items: [], total: 0, offset: 0, limit: 20, rating_average: null, review_count: 0,
  }));
  await page.route('**/api/v1/med/nutr/2048', (route) => fulfillJson(route, SEARCH_PRODUCT));
  await page.route('**/api/v1/med/nutr?*', (route) => fulfillJson(route, {
    items: [SEARCH_PRODUCT], total: 1, offset: 0, limit: 20,
  }));
  await page.route('**/api/v1/users/me', (route) => fulfillJson(route, {
    name: '테스트 사용자', maskedName: '테*트', phoneNumber: null, birthDate: null, gender: null,
  }));
}

test('긴 제품 이름은 랭킹·검색·제품 상세·추가 시트에서 전체가 보인다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  test.setTimeout(120_000);
  await routeProducts(page);

  for (const width of [320, 375, 430, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/supplements?tab=browse');

    const ranking = page.getByLabel('영양제 랭킹');
    const rankingRow = ranking.getByRole('listitem').first();
    await expectContained(rankingRow.getByText(RANKING_NAME, { exact: true }), rankingRow);
    await expect(rankingRow.getByText('등록됨', { exact: true })).toBeVisible();

    await page.getByPlaceholder('제품명 또는 성분 검색').fill('초고함량');
    const results = page.getByLabel('영양제 검색 결과');
    const resultRow = results.getByRole('button', { name: new RegExp(PRODUCT_NAME) });
    await expectContained(resultRow.getByText(PRODUCT_NAME, { exact: true }), resultRow);
    expect((await resultRow.locator('svg').last().boundingBox())!.width).toBe(20);
    await resultRow.click();

    const title = page.getByRole('heading', { name: PRODUCT_NAME, exact: true });
    await expectContained(title, page.locator('main'));
    await page.getByRole('button', { name: '내 영양제에 추가' }).click();
    const addSheet = page.getByRole('dialog', { name: '영양제 추가' });
    const selectedProduct = addSheet.getByRole('listitem').filter({ hasText: PRODUCT_NAME });
    await expectContained(selectedProduct.getByText(PRODUCT_NAME, { exact: true }), selectedProduct);
    await expect(addSheet.getByLabel('선택됨')).toBeVisible();
    expect((await addSheet.getByLabel('선택됨').boundingBox())!.width).toBe(32);
    expect(await addSheet.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    await addSheet.getByRole('button', { name: '닫기' }).click();
  }
});
