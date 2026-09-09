import { expect, test, type Page } from 'playwright/test';

const ACCESS_TOKEN = 'e2e-353-supplement-add-followup';
const PRODUCT_ID = 'sp-001';
const PRODUCT_NAME = '센트룸 실버 우먼';

test.setTimeout(60_000);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(({ token, principal }) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', principal);
  }, {
    token: ACCESS_TOKEN,
    principal: `supplement-add-followup-${Date.now()}-${Math.random()}@example.com`,
  });
});

for (const viewport of [
  { name: 'mobile-320', width: 320, height: 720 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'desktop-1280', width: 1280, height: 900 },
] as const) {
  test(`직접 입력 제품명의 focused 경계를 스크롤 영역 안에 보존한다: ${viewport.name}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await openOrdinaryAddSheet(page);

    const sheet = page.getByRole('dialog', { name: '영양제 추가' });
    await sheet.getByRole('button', { name: '직접 입력', exact: true }).click();
    const manualName = sheet.getByRole('textbox', { name: '직접 입력 제품명' });
    await manualName.fill('통 앞면의 제품명');
    await manualName.focus();
    await expect(manualName).toBeFocused();

    const bounds = await manualName.evaluate((input) => {
      const inputRect = input.getBoundingClientRect();
      const scrollArea = input.closest('section');
      const scrollRect = scrollArea?.getBoundingClientRect();
      const style = getComputedStyle(input);
      return {
        inputLeft: inputRect.left,
        inputRight: inputRect.right,
        scrollLeft: scrollRect?.left ?? null,
        scrollRight: scrollRect?.right ?? null,
        boxShadow: style.boxShadow,
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
      };
    });

    expect(bounds.scrollLeft).not.toBeNull();
    expect(bounds.scrollRight).not.toBeNull();
    if (bounds.scrollLeft === null || bounds.scrollRight === null) {
      throw new Error('직접 입력 스크롤 영역을 찾지 못했습니다.');
    }
    expect(bounds.inputLeft - bounds.scrollLeft).toBeGreaterThanOrEqual(2);
    expect(bounds.scrollRight - bounds.inputRight).toBeGreaterThanOrEqual(2);
    expect(bounds.boxShadow).toContain('0px 0px 0px 2px');
    expect(bounds.documentWidth).toBe(bounds.viewportWidth);

    if (viewport.width === 320) {
      await page.screenshot({
        path: testInfo.outputPath('353-manual-product-focused-320.png'),
        fullPage: true,
        animations: 'disabled',
      });
    }
  });
}

test('같은 검색 제품의 이름 영역을 다시 누르면 설정 폼만 접고 다시 펼칠 수 있다', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openOrdinaryAddSheet(page);
  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('센트룸');

  const product = sheet.getByRole('listitem').filter({ hasText: PRODUCT_NAME });
  const productHeader = product.getByRole('button', { name: new RegExp(PRODUCT_NAME) });
  await productHeader.click();
  await expect(productHeader).toHaveAttribute('aria-expanded', 'true');
  await expect(product.getByRole('button', { name: '추가하기' })).toBeVisible();

  await productHeader.click();
  await expect(productHeader).toHaveAttribute('aria-expanded', 'false');
  await expect(product.getByRole('button', { name: '추가하기' })).toHaveCount(0);

  await productHeader.click();
  await expect(productHeader).toHaveAttribute('aria-expanded', 'true');
  await product.getByRole('button', { name: '1회 섭취량 늘리기' }).click();
  await expect(productHeader).toHaveAttribute('aria-expanded', 'true');
  await product.getByRole('button', { name: '점심' }).click();
  await expect(productHeader).toHaveAttribute('aria-expanded', 'true');

  const otherProduct = sheet.getByRole('listitem').filter({ hasText: '센트룸 실버 맨' });
  const otherHeader = otherProduct.getByRole('button', { name: /센트룸 실버 맨/ });
  await otherHeader.click();
  await expect(productHeader).toHaveAttribute('aria-expanded', 'false');
  await expect(otherHeader).toHaveAttribute('aria-expanded', 'true');
  await page.screenshot({
    path: testInfo.outputPath('353-search-product-switched-390.png'),
    fullPage: true,
    animations: 'disabled',
  });
});

test('제품 정보에서 연 preset 추가는 검색창 없이 열리고 닫았다 다시 열어도 같은 모드다', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(`/dev/supplements/product/${PRODUCT_ID}`);
  await expect(page.getByRole('heading', { name: PRODUCT_NAME })).toBeVisible();

  await page.getByRole('button', { name: '내 영양제에 추가' }).click();
  let sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await expect(sheet.getByRole('searchbox', { name: '영양제 제품 검색' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: new RegExp(PRODUCT_NAME) })).toHaveAttribute(
    'aria-expanded',
    'true',
  );

  await sheet.getByRole('button', { name: '닫기' }).click();
  await page.getByRole('button', { name: '내 영양제에 추가' }).click();
  sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await expect(sheet.getByRole('searchbox', { name: '영양제 제품 검색' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: new RegExp(PRODUCT_NAME) })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await page.screenshot({
    path: testInfo.outputPath('353-preset-product-no-search-320.png'),
    fullPage: true,
    animations: 'disabled',
  });
});

test('내 영양제의 일반 추가 흐름은 검색창을 유지한다', async ({ page }) => {
  await openOrdinaryAddSheet(page);
  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await expect(sheet.getByRole('searchbox', { name: '영양제 제품 검색' })).toBeVisible();
});

async function openOrdinaryAddSheet(page: Page) {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).last().click();
  await expect(page.getByRole('dialog', { name: '영양제 추가' })).toBeVisible();
}
