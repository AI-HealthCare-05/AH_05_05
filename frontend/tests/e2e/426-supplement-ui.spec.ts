import { expect, test, type Page, type Route } from 'playwright/test';

const LONG_RANKING_NAME = `매일 챙겨 먹는 ${'아주긴영양제이름'.repeat(8)}`;

const PRODUCT = {
  id: 701,
  food_code: 'SUPPL-426-701',
  name: '테스트 종합 영양제',
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
  vitamin_d_ug: null,
  cholesterol_mg: null,
  sat_fat_g: null,
  trans_fat_g: null,
  serving_desc: '2정',
  serving_size: '1000mg',
  daily_freq: '2회',
  target: '성인',
  rating_average: 4.6,
  review_count: 2,
};

const ACTIVE_REGISTRATION = {
  id: 9001,
  custom_name: null,
  dose_amount: '2.000',
  dose_unit: '정',
  start_date: '2026-09-01',
  end_date: null,
  status: 'ACTIVE',
  score: 4,
  review_body: null,
  note: '띄어쓰기없는긴메모'.repeat(15),
  created_at: '2026-09-01T09:00:00+09:00',
  updated_at: null,
  slots: [
    { slot: 'MORNING', time: '08:00:00' },
    { slot: 'EVENING', time: '19:00:00' },
  ],
  supplement: PRODUCT,
};

const RANKING = {
  display_id: 426,
  title: '추석선물 추천 영양제',
  start_at: '2026-09-01T00:00:00+09:00',
  end_at: '2026-09-30T23:59:59+09:00',
  is_enabled: true,
  created_by_admin_id: 1,
  created_at: '2026-09-01T00:00:00+09:00',
  updated_at: null,
  items: [{ supplement_nutrient_id: 701, name: LONG_RANKING_NAME, rank_no: 1 }],
};

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-426-token');
    sessionStorage.setItem('poke.account-principal', 'issue-426@example.com');
  });
}

async function routeSupplementList(page: Page, registration = ACTIVE_REGISTRATION) {
  const requests: URL[] = [];
  await page.route('**/api/v1/med/user-suppl-nutr?*', async (route) => {
    requests.push(new URL(route.request().url()));
    await fulfillJson(route, {
      items: [registration],
      total: 1,
      offset: 0,
      limit: 100,
      nutrient_standard: null,
    });
  });
  return requests;
}

test.beforeEach(async ({ page }) => {
  await authenticate(page);
});

test('선택한 정렬명은 방향을 표시하고 후기 수와 현재 복용 상태를 명확히 설명한다', async ({
  page,
}, testInfo) => {
  const listRequests = await routeSupplementList(page);
  await page.route('**/api/v1/display/med/nutr/rank', (route) => fulfillJson(route, RANKING));
  await page.route('**/api/v1/med/nutr?*', (route) =>
    fulfillJson(route, { items: [PRODUCT], total: 1, offset: 0, limit: 20 }),
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dev/supplements?tab=browse');

  const ranking = page.getByRole('region', { name: '영양제 랭킹' });
  await expect(ranking.getByText('복용 중', { exact: true })).toBeVisible();
  await expect(ranking.getByText('등록됨', { exact: true })).toHaveCount(0);
  const rankingName = ranking.getByText(LONG_RANKING_NAME, { exact: true });
  await expect(rankingName).toHaveAttribute('title', LONG_RANKING_NAME);
  const rankingStyle = await rankingName.evaluate((element) => {
    const style = getComputedStyle(element);
    return { textOverflow: style.textOverflow, whiteSpace: style.whiteSpace };
  });
  expect(rankingStyle).toEqual({ textOverflow: 'ellipsis', whiteSpace: 'nowrap' });

  await page.getByPlaceholder('제품명 또는 성분 검색').fill('테스트');
  const sorts = page.getByRole('group', { name: '검색 결과 정렬' });
  await expect(sorts.getByText('이름순 ▲', { exact: true })).toBeVisible();
  await expect(page.getByText('★4.6 · 후기: 2개', { exact: true })).toBeVisible();
  await expect(page.getByLabel('영양제 검색 결과').getByText('복용 중', { exact: true })).toBeVisible();

  await page.getByRole('group', { name: '정렬 방향' }).getByRole('button', { name: '내림차순' }).click();
  await expect(sorts.getByText('이름순 ▼', { exact: true })).toBeVisible();
  expect(listRequests.length).toBeGreaterThan(0);
  expect(listRequests.every((request) => request.searchParams.get('status') === 'ACTIVE')).toBe(true);

  await page.screenshot({ path: testInfo.outputPath('426-browse-390-green.png'), fullPage: true });
});

test('내 영양제 목록은 복용 정보를 줄로 나누고 정상 상태에서는 추가 동작을 하나만 제공한다', async ({
  page,
}) => {
  await routeSupplementList(page, {
    ...ACTIVE_REGISTRATION,
    supplement: null,
    custom_name: '직접 입력 테스트 영양제',
  });

  await page.goto('/dev/supplements');
  const list = page.getByRole('region', { name: '먹고 있는 영양제' });
  const row = list.getByRole('button', { name: /직접 입력 테스트 영양제/ });
  await expect(row.getByText('하루 2회 · 1회 2정', { exact: true })).toBeVisible();
  await expect(row.getByText('아침 · 저녁', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '영양제 추가', exact: true })).toHaveCount(1);
  await expect(page.getByText('성분 정보 없음', { exact: true })).toHaveCount(0);

  await row.click();
  const editor = page.getByRole('dialog', { name: '직접 입력 테스트 영양제' });
  const summary = editor.getByRole('region', { name: '내 영양제 요약' });
  await expect(summary.getByLabel('별 4점')).toHaveCount(0);
  await expect(summary.getByText('메모 있음', { exact: false })).toHaveCount(0);
  await expect(editor.getByText('성분 정보 없음', { exact: true })).toHaveCount(0);

  const memoText = editor.getByRole('group', { name: '내 메모' }).locator('p');
  const memoFits = await memoText.evaluate(
    (element) => element.scrollWidth <= element.clientWidth + 1,
  );
  expect(memoFits).toBe(true);
});

async function openSelectedProduct(
  page: Page,
  products: Array<typeof PRODUCT> = [PRODUCT],
  selectedProduct = products[0],
) {
  await routeSupplementList(page);
  await page.route('**/api/v1/med/nutr?*', (route) =>
    fulfillJson(route, { items: products, total: products.length, offset: 0, limit: 20 }),
  );

  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).first().click();
  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('테스트');
  const product = sheet.getByRole('listitem').filter({ hasText: selectedProduct.name });
  await product.getByRole('button', { name: new RegExp(selectedProduct.name) }).click();
  return { product, sheet };
}

test('추가 시트는 제품 정보의 복용 권장사항을 안내한다', async ({ page }) => {
  const { product } = await openSelectedProduct(page);

  await expect(product.getByText('제품 정보의 복용 권장사항을 참고하세요.', { exact: true })).toBeVisible();
});

test('마지막으로 누른 복용 시간도 다른 선택 시간과 같은 배경을 유지한다', async ({ page }) => {
  const { product } = await openSelectedProduct(page);
  const lunch = product.getByRole('button', { name: '점심', exact: true });
  await lunch.click();
  await lunch.hover();
  const selectedBackgrounds = await product
    .getByRole('group', { name: '복용 시간' })
    .locator('button[aria-pressed="true"]')
    .evaluateAll((buttons) => buttons.map((button) => getComputedStyle(button).backgroundImage));
  expect(new Set(selectedBackgrounds).size).toBe(1);
  await lunch.focus();
  await expect(lunch).toBeFocused();
});

test('작은 화면에서 선택한 제품 카드의 상세 정보와 추가 버튼이 잘리지 않는다', async ({
  page,
}, testInfo) => {
  const products = Array.from({ length: 6 }, (_, index) => ({
    ...PRODUCT,
    id: PRODUCT.id + index,
    name: `테스트 영양제 ${index + 1}`,
  }));
  const { product, sheet } = await openSelectedProduct(page, products, products.at(-1)!);

  const cardMetrics = await product.locator('article').evaluate((article) => {
    const list = article.closest('ul');
    if (!list) return null;
    const cardRect = article.getBoundingClientRect();
    const listRect = list.getBoundingClientRect();
    return {
      cardTop: cardRect.top,
      cardBottom: cardRect.bottom,
      cardHeight: cardRect.height,
      cardClientHeight: article.clientHeight,
      cardScrollHeight: article.scrollHeight,
      listTop: listRect.top,
      listBottom: listRect.bottom,
      listHeight: listRect.height,
    };
  });
  expect(cardMetrics).not.toBeNull();
  expect(cardMetrics!.cardTop).toBeGreaterThanOrEqual(cardMetrics!.listTop - 1);
  expect(cardMetrics!.cardBottom).toBeLessThanOrEqual(cardMetrics!.listBottom + 1);
  await expect(product.getByRole('button', { name: '추가하기' })).toBeVisible();
  await expect(sheet).toBeVisible();

  await page.screenshot({ path: testInfo.outputPath('426-add-sheet-375-green.png'), fullPage: true });
});

test('제품 상세는 없는 정보를 숨기고 복용 정보를 중복 없는 평면 영역으로 표시한다', async ({
  page,
}, testInfo) => {
  await routeSupplementList(page, { ...ACTIVE_REGISTRATION, supplement: null });
  await page.route('**/api/v1/med/nutr/701', (route) =>
    fulfillJson(route, { ...PRODUCT, target: null }),
  );
  await page.route('**/api/v1/med/nutr/701/reviews?*', (route) =>
    fulfillJson(route, {
      items: [],
      total: 0,
      offset: 0,
      limit: 10,
      rating_average: null,
      review_count: 0,
    }),
  );

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/dev/supplements/product/701');

  const info = page.getByRole('region', { name: '제품 정보 상세' });
  await expect(info).toBeVisible();
  await expect(info.getByText('섭취 대상', { exact: true })).toHaveCount(0);
  await expect(page.getByText('섭취 대상 정보 없음', { exact: true })).toHaveCount(0);
  await expect(info.getByText('2정', { exact: true })).toBeVisible();
  await expect(info.getByText('2회', { exact: true })).toBeVisible();
  const occurrenceCount = await page.locator('main').evaluate(
    (main) => main.innerText.match(/2정/g)?.length ?? 0,
  );
  expect(occurrenceCount).toBe(1);
  const infoStyle = await info.evaluate((element) => {
    const style = getComputedStyle(element);
    return { borderRadius: style.borderRadius, boxShadow: style.boxShadow };
  });
  expect(infoStyle.borderRadius).toBe('0px');
  expect(infoStyle.boxShadow).toBe('none');

  await page.screenshot({ path: testInfo.outputPath('426-product-1280-green.png'), fullPage: true });
});
