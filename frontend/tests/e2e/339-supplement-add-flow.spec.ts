import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const ACCESS_TOKEN = 'e2e-339-supplement-add-token';
const PRODUCT_ID = 33901;
const PRODUCT_NAME = '검색해서 추가하는 종합비타민';

const PRODUCT_RESPONSE = {
  id: PRODUCT_ID,
  food_code: 'SUPPL-339-01',
  name: PRODUCT_NAME,
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
  serving_desc: '1정',
  serving_size: '1000mg',
  daily_freq: '1회',
  target: '성인',
  rating_average: '4.5',
  review_count: 2,
};

const REGISTRATION_RESPONSE = {
  id: 9339,
  custom_name: null,
  dose_amount: '1.000',
  dose_unit: '정',
  start_date: '2026-09-08',
  end_date: null,
  status: 'ACTIVE',
  score: null,
  review_body: null,
  note: null,
  created_at: '2026-09-08T09:00:00+09:00',
  updated_at: null,
  slots: [{ slot: 'MORNING', time: '08:00:00' }],
  supplement: PRODUCT_RESPONSE,
};

test.setTimeout(60_000);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(({ token, principal }) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', principal);
  }, {
    token: ACCESS_TOKEN,
    principal: `supplement-add-339-${Date.now()}-${Math.random()}@example.com`,
  });
});

test('목업 검색에서 제품을 추가하면 내 영양제로 이동하고 새 제품을 목록에 보여준다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, '목업 저장소까지 포함한 전체 추가 흐름 테스트입니다.');

  await page.goto('/dev/supplements?tab=browse');
  await page.getByPlaceholder('제품명 또는 성분 검색').fill('센트룸 실버 우먼');
  const results = page.getByRole('region', { name: '영양제 검색 결과' });
  await results.getByRole('button', { name: /센트룸 실버 우먼/ }).click();

  await expect(page).toHaveURL(/\/dev\/supplements\/product\/sp-001$/);
  await page.getByRole('button', { name: '내 영양제에 추가' }).click();
  const addSheet = page.getByRole('dialog', { name: '영양제 추가' });
  await addSheet.getByRole('button', { name: '추가하기' }).click();

  await expect(page).toHaveURL(/\/dev\/supplements$/);
  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await expect(tabs.getByRole('button', { name: '내 영양제' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  const mySupplements = page.getByRole('region', { name: /먹고 있는 영양제/ });
  await expect(mySupplements.getByRole('button', { name: /센트룸 실버 우먼/ })).toBeVisible();
});

test('실 API 경계에서 저장이 성공하면 목록을 다시 조회해 새 제품을 보여준다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await installRealApi(page);

  await openRealProductFromSearch(page);
  await page.getByRole('button', { name: '내 영양제에 추가' }).click();
  const addSheet = page.getByRole('dialog', { name: '영양제 추가' });
  await addSheet.getByRole('button', { name: '추가하기' }).click();

  await expect(page).toHaveURL(/\/supplements$/);
  const tabs = page.getByRole('group', { name: '영양제 화면' });
  await expect(tabs.getByRole('button', { name: '내 영양제' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  const mySupplements = page.getByRole('region', { name: /먹고 있는 영양제/ });
  await expect(mySupplements.getByRole('button', { name: new RegExp(PRODUCT_NAME) })).toBeVisible();
});

test('실 API 저장이 실패하면 제품 상세와 추가 시트를 유지하고 오류를 보여준다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await installRealApi(page, { saveFails: true });

  await openRealProductFromSearch(page);
  await page.getByRole('button', { name: '내 영양제에 추가' }).click();
  const addSheet = page.getByRole('dialog', { name: '영양제 추가' });
  await addSheet.getByRole('button', { name: '추가하기' }).click();

  const errorDialog = page.getByRole('dialog', { name: '영양제를 추가하지 못했어요' });
  await expect(errorDialog.getByText('저장 실패를 확인해 주세요.')).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/supplements/product/${PRODUCT_ID}$`));

  await errorDialog.getByRole('button', { name: '확인' }).click();
  await expect(page.getByRole('dialog', { name: '영양제 추가' })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/supplements/product/${PRODUCT_ID}$`));
});

test('저장 응답 전에 상세를 떠나면 늦은 성공이 현재 화면을 빼앗지 않는다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  let markSaveStarted!: () => void;
  const saveStarted = new Promise<void>((resolve) => {
    markSaveStarted = resolve;
  });
  let releaseSave!: () => void;
  const saveRelease = new Promise<void>((resolve) => {
    releaseSave = resolve;
  });
  await installRealApi(page, {
    beforeSaveResponse: async () => {
      markSaveStarted();
      await saveRelease;
    },
  });

  await openRealProductFromSearch(page);
  await page.getByRole('button', { name: '내 영양제에 추가' }).click();
  const addSheet = page.getByRole('dialog', { name: '영양제 추가' });
  await addSheet.getByRole('button', { name: '추가하기' }).click();
  await saveStarted;

  await addSheet.getByRole('button', { name: '닫기' }).click();
  await page.getByRole('banner').getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/supplements\?tab=browse$/);

  const saveResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      response.url().endsWith(`/api/v1/med/user-suppl-nutr/${PRODUCT_ID}`),
  );
  releaseSave();
  await saveResponse;
  await page.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
  await expect(page).toHaveURL(/\/supplements\?tab=browse$/);
});

async function openRealProductFromSearch(page: Page) {
  await page.goto('/supplements?tab=browse');
  await page.getByPlaceholder('제품명 또는 성분 검색').fill(PRODUCT_NAME);
  const results = page.getByRole('region', { name: '영양제 검색 결과' });
  await results.getByRole('button', { name: new RegExp(PRODUCT_NAME) }).click();
  await expect(page).toHaveURL(new RegExp(`/supplements/product/${PRODUCT_ID}$`));
  await expect(page.getByRole('heading', { name: PRODUCT_NAME })).toBeVisible();
}

async function installRealApi(
  page: Page,
  {
    saveFails = false,
    beforeSaveResponse,
  }: { saveFails?: boolean; beforeSaveResponse?: () => Promise<void> } = {},
) {
  let saved = false;

  await page.route('**/api/v1/med/user-suppl-nutr?*', (route) =>
    fulfillJson(route, {
      items: saved ? [REGISTRATION_RESPONSE] : [],
      total: saved ? 1 : 0,
      offset: 0,
      limit: 100,
      nutrient_standard: null,
    }),
  );
  await page.route(`**/api/v1/med/user-suppl-nutr/${PRODUCT_ID}`, async (route) => {
    await beforeSaveResponse?.();
    if (saveFails) {
      await fulfillJson(
        route,
        { code: 'supplement_save_failed', message: '저장 실패를 확인해 주세요.' },
        500,
      );
      return;
    }
    saved = true;
    await fulfillJson(route, REGISTRATION_RESPONSE);
  });
  await page.route('**/api/v1/med/nutr?*', (route) =>
    fulfillJson(route, {
      items: [PRODUCT_RESPONSE],
      total: 1,
      offset: 0,
      limit: 20,
    }),
  );
  await page.route(`**/api/v1/med/nutr/${PRODUCT_ID}`, (route) =>
    fulfillJson(route, PRODUCT_RESPONSE),
  );
  await page.route(`**/api/v1/med/nutr/${PRODUCT_ID}/reviews?*`, (route) =>
    fulfillJson(route, {
      items: [],
      total: 0,
      offset: 0,
      limit: 10,
      rating_average: PRODUCT_RESPONSE.rating_average,
      review_count: PRODUCT_RESPONSE.review_count,
    }),
  );
  await page.route('**/api/v1/display/med/nutr/rank', (route) =>
    fulfillJson(route, { code: 'not_found', message: '랭킹이 없습니다.' }, 404),
  );
  await page.route('**/api/v1/users/me', (route) =>
    fulfillJson(route, {
      name: '테스트 사용자',
      maskedName: '테***자',
      phoneNumber: '01012345678',
      birthDate: '2000-01-01',
      gender: 'FEMALE',
    }),
  );
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}
