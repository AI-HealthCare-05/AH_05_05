import { expect, test } from 'playwright/test';

const IS_REAL_API = process.env.VITE_USE_MOCK === 'false';

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
  rating_average: null,
  review_count: 0,
};

test('제품 상세는 섭취 정보와 성분을 보여주고 기준선 바는 그리지 않는다', async ({ page }) => {
  test.skip(IS_REAL_API, '고정 제품 데이터로 상세 표시를 확인하는 목업 전용 테스트입니다.');
  await page.goto('/dev/supplements/product/sp-001');

  await expect(page.getByRole('heading', { name: '제품 정보' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '센트룸 실버 우먼' })).toBeVisible();
  await expect(page.getByText('한국화이자 · 1정 · 1회', { exact: true })).toBeVisible();
  const nutrients = page.getByLabel('제품 성분');
  await expect(nutrients.getByText('비타민 A', { exact: true })).toBeVisible();
  await expect(nutrients.getByText('400 µg RAE', { exact: true })).toBeVisible();
  await expect(page.getByRole('meter')).toHaveCount(0);
  await expect(page.getByText('준비 중', { exact: false })).toHaveCount(0);
});

test('등록하지 않은 제품은 기존 preset 추가 시트를 연다', async ({ page }) => {
  test.skip(IS_REAL_API, '목업 제품의 preset 추가 흐름을 확인하는 테스트입니다.');
  await page.goto('/dev/supplements/product/sp-001');

  await page.getByRole('button', { name: '내 영양제에 추가' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: '영양제 추가' })).toBeVisible();
  await expect(dialog.getByText('센트룸 실버 우먼', { exact: true })).toBeVisible();
  await expect(dialog.getByRole('button', { name: '추가하기' })).toBeVisible();
});

test('이미 등록한 제품은 내 영양제에서 보기로 돌아간다', async ({ page }) => {
  test.skip(IS_REAL_API, '목업 등록 제품 상태를 확인하는 테스트입니다.');
  await page.goto('/dev/supplements/product/mock-501');

  await page.getByRole('button', { name: '내 영양제에서 보기' }).click();

  await expect(page).toHaveURL(/\/supplements$/);
});
test('실 API 모드에서도 제품 상세 응답과 등록 상태를 함께 읽는다', async ({ page }) => {
  test.skip(!IS_REAL_API, '실 API 모드의 상세·등록 목록 계약을 확인하는 테스트입니다.');
  await page.route('**/api/v1/med/nutr/2048', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(PRODUCT_RESPONSE),
    }),
  );
  await page.route('**/api/v1/med/user-suppl-nutr?*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
        total: 0,
        offset: 0,
        limit: 100,
        nutrient_standard: null,
      }),
    }),
  );

  await page.goto('/dev/supplements/product/2048');

  await expect(page.getByRole('heading', { name: '종합비타민' })).toBeVisible();
  await expect(page.getByText('성인 · 2정 · 1회', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '내 영양제에 추가' })).toBeVisible();
});
