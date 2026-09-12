import { expect, test, type Page, type Route } from 'playwright/test';

import { waitForVisibleImages } from './helpers/visibleImages';

const PRODUCT = {
  id: 701, food_code: 'SUPPL-426-701', name: 'EYE100 테스트 제품', basis_qty: '1000mg',
  energy_kcal: 0, water_g: null, protein_g: null, fat_g: null, ash_g: null,
  carb_g: null, sugar_g: null, fiber_g: null, calcium_mg: '100.00', iron_mg: null,
  phosphorus_mg: null, potassium_mg: null, sodium_mg: null, vitamin_a_ug_rae: null,
  retinol_ug: null, beta_carotene_ug: null, thiamine_mg: null, riboflavin_mg: null,
  niacin_mg: null, vitamin_c_mg: null, vitamin_d_ug: null, cholesterol_mg: null,
  sat_fat_g: null, trans_fat_g: null, serving_desc: '2정', serving_size: '1000mg',
  daily_freq: '2회', target: '성인', rating_average: null, review_count: 0,
};

async function json(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function openProduct(page: Page, overrides: Record<string, string | null> = {}) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-426-panel-fixture');
    sessionStorage.setItem('poke.account-principal', 'issue-426-panel@example.com');
  });
  await page.route((url) => /^\/(api|media)(\/|$)/.test(url.pathname),
    (route) => route.fulfill({ status: 503, body: 'Fixture not defined' }));
  await page.route('**/api/v1/med/nutr/701', (route) => json(route, { ...PRODUCT, ...overrides }));
  await page.route('**/api/v1/med/user-suppl-nutr?*', (route) => json(route, {
    items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null,
  }));
  await page.route('**/api/v1/med/nutr/701/reviews?*', (route) => json(route, {
    items: [], total: 0, offset: 0, limit: 10, rating_average: null, review_count: 0,
  }));
  await page.goto('/dev/supplements/product/701');
  await expect(page.getByRole('heading', { name: PRODUCT.name })).toBeVisible({ timeout: 60_000 });
}

for (const width of [375, 390, 1280]) {
  // Catches a transparent, flush-to-edge information section or accidental Card clay styling.
  test(`제품 정보는 흰 사각 패널로 구분하고 성분 카드 입체감은 보존한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 1280 ? 900 : 844 });
    await openProduct(page);
    const info = page.getByRole('region', { name: '제품 정보 상세' });
    await expect(info).toBeVisible();
    await expect(info.locator('dt')).toHaveText(['섭취 대상', '1회 섭취량', '하루 섭취 횟수']);
    await expect(info.locator('dd')).toHaveText(['성인', '2정', '2회']);
    for (const value of ['성인', '2정', '2회']) {
      await expect(page.locator('main').getByText(value, { exact: true })).toHaveCount(1);
    }
    const style = await info.evaluate((element) => {
      const css = getComputedStyle(element);
      const pageCss = getComputedStyle(element.closest('main')!.parentElement!);
      return {
        background: css.backgroundColor, pageBackground: pageCss.backgroundColor,
        paddingLeft: css.paddingLeft, paddingRight: css.paddingRight,
        borders: [css.borderTopWidth, css.borderRightWidth, css.borderBottomWidth, css.borderLeftWidth],
        borderStyle: css.borderStyle, borderColor: css.borderColor,
        radius: css.borderRadius, shadow: css.boxShadow, image: css.backgroundImage,
      };
    });
    expect(style.background).toBe('rgb(255, 255, 255)');
    expect(style.background).not.toBe(style.pageBackground);
    expect(style.paddingLeft).toBe('16px');
    expect(style.paddingRight).toBe('16px');
    expect(style.borders).toEqual(['1px', '1px', '1px', '1px']);
    expect(style.borderStyle).toBe('solid');
    expect(style.borderColor).not.toBe('rgba(0, 0, 0, 0)');
    expect(style.radius).toBe('0px');
    expect(style.shadow).toBe('none');
    expect(style.image).toBe('none');

    const ingredients = page.getByRole('region', { name: '성분', exact: true });
    await expect(ingredients.getByText('50 mg', { exact: true })).toBeVisible();
    const cardStyle = await ingredients.locator('.rx-card').evaluate((card) => {
      const css = getComputedStyle(card);
      return { radius: css.borderRadius, shadow: css.boxShadow, image: css.backgroundImage };
    });
    expect(parseFloat(cardStyle.radius)).toBeGreaterThan(0);
    expect(cardStyle.shadow).not.toBe('none');
    expect(cardStyle.image).toContain('linear-gradient');
    await waitForVisibleImages(page);
    await page.screenshot({ path: testInfo.outputPath(`426-product-info-panel-${width}.png`), fullPage: true });
  });
}

test('누락된 제품 정보 행과 모든 정보가 없는 빈 패널을 숨긴다', async ({ page }) => {
  await openProduct(page, { target: null, daily_freq: '정보 없음' });
  const info = page.getByRole('region', { name: '제품 정보 상세' });
  await expect(info.locator('dt')).toHaveText(['1회 섭취량']);
  await expect(info.locator('dd')).toHaveText(['2정']);
  await expect(page.getByText('정보 없음', { exact: false })).toHaveCount(0);
  await page.route('**/api/v1/med/nutr/701', (route) => json(route, {
    ...PRODUCT, target: null, serving_desc: ' ', serving_size: '', daily_freq: '-',
  }));
  await page.reload();
  await expect(page.getByRole('heading', { name: PRODUCT.name })).toBeVisible();
  await expect(info).toHaveCount(0);
  await expect(page.getByLabel('제품 성분')).toBeVisible();
});

for (const width of [375, 390, 1280]) {
  test(`공백 없는 긴 제품 정보가 패널 여백 안에서 줄바꿈한다 (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await openProduct(page, {
      target: 'LONGTARGET426'.repeat(18), serving_desc: 'LONGSERVING426'.repeat(18),
      daily_freq: 'LONGFREQUENCY426'.repeat(18),
    });
    const info = page.getByRole('region', { name: '제품 정보 상세' });
    const fits = await info.evaluate((element) => {
      const panel = element.getBoundingClientRect();
      const css = getComputedStyle(element);
      return [...element.querySelectorAll('dd')].every((value) => {
        const rect = value.getBoundingClientRect();
        return value.scrollWidth <= value.clientWidth + 1
          && rect.left >= panel.left + parseFloat(css.paddingLeft)
          && rect.right <= panel.right - parseFloat(css.paddingRight)
          && rect.height > parseFloat(getComputedStyle(value).lineHeight);
      }) && element.scrollWidth <= element.clientWidth + 1;
    });
    expect(fits).toBe(true);
    expect(await page.locator('main').evaluate((main) => main.scrollWidth <= main.clientWidth + 1)).toBe(true);
  });
}
