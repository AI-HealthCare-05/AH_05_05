import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

const PRODUCT = {
  id: 701, food_code: 'SUPPL-426-701', name: '테스트 영양제', basis_qty: '1000mg',
  energy_kcal: 0, water_g: null, protein_g: null, fat_g: null, ash_g: null,
  carb_g: null, sugar_g: null, fiber_g: null, calcium_mg: '100.00', iron_mg: null,
  phosphorus_mg: null, potassium_mg: null, sodium_mg: null, vitamin_a_ug_rae: null,
  retinol_ug: null, beta_carotene_ug: null, thiamine_mg: null, riboflavin_mg: null,
  niacin_mg: null, vitamin_c_mg: null, vitamin_d_ug: null, cholesterol_mg: null,
  sat_fat_g: null, trans_fat_g: null, serving_desc: '2정', serving_size: '1000mg',
  daily_freq: '2회', target: '성인', rating_average: 4.6, review_count: 2,
};

async function json(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function openSearch(page: Page, longName?: string) {
  const products = Array.from({ length: 22 }, (_, index) => ({
    ...PRODUCT, id: 701 + index,
    name: longName ?? (index % 2 ? `데일리 멀티비타민 미네랄 플러스 ${index + 1}` : `테스트 영양제 ${index + 1}`),
  }));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-426-viewport-token');
    sessionStorage.setItem('poke.account-principal', 'issue-426@example.com');
  });
  await page.route('**/api/v1/med/user-suppl-nutr?*', (route) => json(route, {
    items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null,
  }));
  await page.route('**/api/v1/med/nutr?*', (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get('offset') ?? 0);
    return json(route, { items: products.slice(offset, offset + 20), total: 22, offset, limit: 20 });
  });
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await sheet.getByRole('searchbox').fill('테스트');
  await expect(sheet.getByText('22개가 찾아졌어요.')).toBeVisible();
  return { sheet, products, list: sheet.getByRole('list', { name: '검색 결과', exact: true }) };
}

async function geometry(card: Locator) {
  return card.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const list = element.closest('ul')!.getBoundingClientRect();
    return {
      top: rect.top, bottom: rect.bottom, height: rect.height,
      listTop: list.top, listBottom: list.bottom, listHeight: list.height,
      viewportHeight: innerHeight,
      fits: rect.top >= Math.max(list.top, 0) - 1 && rect.bottom <= Math.min(list.bottom, innerHeight) + 1,
      horizontalFit: element.scrollWidth <= element.clientWidth + 1,
    };
  });
}

// Reserving fixed banner/footer height breaks this contract even though toBeVisible passes.
for (const [width, height] of [[320, 568], [375, 667], [360, 800], [393, 852], [390, 700], [1280, 900]]) {
  test(`22 results: selected full card fits ${width}x${height} emulated viewport`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height });
    const { sheet, products, list } = await openSearch(page);
    for (const index of [0, 9, 19, 21]) {
      if (index === 21) await list.evaluate((element) => { element.scrollTop = element.scrollHeight; });
      const card = list.locator('article').filter({ has: page.getByText(products[index].name, { exact: true }) });
      await card.locator('button').first().click();
      await expect(card.locator('button').first()).toHaveAttribute('aria-expanded', 'true');
      await expect.poll(async () => (await geometry(card)).fits).toBe(true);
      const metrics = await geometry(card);
      console.log(JSON.stringify({ viewport: `${width}x${height}`, index, ...metrics }));
      expect(metrics.horizontalFit).toBe(true);
      for (const control of await card.locator('button').all()) {
        expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      }
      await expect(sheet.getByRole('searchbox')).toHaveValue('테스트');
      if (index === 9) await page.screenshot({ path: testInfo.outputPath(`426-selected-${width}x${height}-emulated.png`) });
    }
  });
}

test('selected product stays in view when the viewport shrinks', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  const { list, sheet } = await openSearch(page);
  const card = list.locator('article').nth(9);
  await card.locator('button').first().click();
  await expect.poll(async () => (await geometry(card)).fits).toBe(true);
  await sheet.evaluate((element) => { element.style.paddingBottom = '34px'; });
  await expect.poll(async () => (await geometry(card)).fits).toBe(true);
  await sheet.evaluate((element) => { element.style.removeProperty('padding-bottom'); });
  await page.setViewportSize({ width: 320, height: 568 });
  await expect.poll(async () => (await geometry(card)).fits).toBe(true);
  await card.getByRole('button', { name: '아침', exact: true }).click();
  await card.getByRole('button', { name: '저녁', exact: true }).click();
  await expect(card.getByText('복용 시간을 하나 이상 선택해주세요.')).toBeVisible();
  await expect(card.getByRole('button', { name: '추가하기' })).toBeDisabled();
  await card.getByRole('button', { name: '점심', exact: true }).click();
  await expect(card.getByRole('button', { name: '추가하기' })).toBeEnabled();
  await sheet.getByRole('button', { name: '직접 입력', exact: true }).click();
  await expect(sheet.getByRole('textbox', { name: '직접 입력 제품명' })).toBeVisible();
  await sheet.getByRole('button', { name: '검색으로 돌아가기', exact: true }).click();
  await expect(sheet.getByRole('searchbox')).toHaveValue('테스트');
  await expect(sheet.getByText('22개가 찾아졌어요.')).toBeVisible();
});

test('selected details remain reachable after resize and with 200% text and a very long name', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  const { list } = await openSearch(page, '공백없는아주긴영양제품명'.repeat(15));
  const card = list.locator('article').first();
  await card.locator('button').first().click();
  await page.setViewportSize({ width: 667, height: 375 });
  const name = card.locator('strong').first();
  const originalFontSize = await name.evaluate((element) => parseFloat(getComputedStyle(element).fontSize));
  // The app's type tokens use px, so changing html font-size alone does not enlarge text.
  await card.evaluate((element) => {
    const textStyles = [...element.querySelectorAll<HTMLElement>('*')].map((child) => ({
      child, fontSize: parseFloat(getComputedStyle(child).fontSize),
      lineHeight: parseFloat(getComputedStyle(child).lineHeight),
    }));
    for (const { child, fontSize, lineHeight } of textStyles) {
      child.style.fontSize = `${fontSize * 2}px`;
      if (Number.isFinite(lineHeight)) child.style.lineHeight = `${lineHeight * 2}px`;
    }
  });
  expect(await name.evaluate((element) => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(originalFontSize * 2);
  const add = card.getByRole('button', { name: '추가하기', exact: true });
  await add.scrollIntoViewIfNeeded();
  await expect(add).toBeInViewport({ ratio: 1 });
  expect((await geometry(card)).horizontalFit).toBe(true);
  for (const name of ['1회 섭취량 늘리기', '아침', '점심', '저녁', '자기전']) {
    const control = card.getByRole('button', { name, exact: true });
    await control.scrollIntoViewIfNeeded();
    await expect(control).toBeInViewport({ ratio: 1 });
  }
});

test('manual entry remains available if loading the next page fails after selection', async ({ page }) => {
  const { sheet, list } = await openSearch(page);
  await page.route('**/api/v1/med/nutr?*', (route) => {
    if (Number(new URL(route.request().url()).searchParams.get('offset')) > 0) {
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
    }
    return route.fallback();
  });
  await list.locator('article').first().locator('button').first().click();
  await list.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  await expect(list).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: '직접 입력', exact: true })).toBeVisible();
  await sheet.getByRole('button', { name: '직접 입력', exact: true }).click();
  await expect(sheet.getByRole('textbox', { name: '직접 입력 제품명' })).toBeVisible();
});

test('22-result selection saves the chosen product dose and slots', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-12T03:00:00Z'));
  await page.setViewportSize({ width: 320, height: 568 });
  const { sheet, list, products } = await openSearch(page);
  let saved: unknown;
  await page.route('**/api/v1/med/user-suppl-nutr/701', async (route) => {
    expect(route.request().method()).toBe('PUT');
    saved = route.request().postDataJSON();
    await json(route, {
      id: 9001, custom_name: null, dose_amount: '3.000', dose_unit: '정',
      start_date: '2026-09-12', end_date: null, status: 'ACTIVE', score: null,
      review_body: null, note: null, created_at: '2026-09-12T12:00:00+09:00', updated_at: null,
      slots: [{ slot: 'LUNCH', time: '12:00:00' }], supplement: products[0],
    });
  });
  const card = list.locator('article').first();
  await card.locator('button').first().click();
  await card.getByRole('button', { name: '아침', exact: true }).click();
  await card.getByRole('button', { name: '저녁', exact: true }).click();
  await card.getByRole('button', { name: '점심', exact: true }).click();
  await card.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await card.getByRole('button', { name: '추가하기', exact: true }).click();
  await expect(sheet).toBeHidden();
  expect(saved).toEqual({
    dose_amount: 3, dose_unit: '정', start_date: '2026-09-12', end_date: null,
    slots: ['LUNCH'], note: null,
  });
});
