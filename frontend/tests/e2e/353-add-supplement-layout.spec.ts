import { expect, test } from 'playwright/test';

test.setTimeout(60_000);

const VIEWPORTS = [
  { name: 'mobile-320', width: 320, height: 720 },
  { name: 'mobile-375', width: 375, height: 812 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'desktop-1280', width: 1280, height: 900 },
] as const;

for (const viewport of VIEWPORTS) {
  test(`영양제 검색창 양끝 affordance와 focused 경계를 보존한다: ${viewport.name}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.goto('/dev/supplements');
    await page.getByRole('button', { name: '영양제 추가', exact: true }).last().click();

    const sheet = page.getByRole('dialog', { name: '영양제 추가' });
    const search = sheet.getByRole('searchbox', { name: '영양제 제품 검색' });
    const searchIcon = sheet.locator('svg.lucide-search');
    await search.fill('센트룸 종합비타민');
    await search.focus();
    await expect(search).toBeFocused();
    await expect(search).toHaveAttribute('type', 'search');
    await expect(search).toHaveValue('센트룸 종합비타민');

    const measurements = await search.evaluate((input) => {
      const inputRect = input.getBoundingClientRect();
      const inputStyle = getComputedStyle(input);
      const sheetElement = input.closest('[data-slot="dialog-content"]');
      const sheetRect = sheetElement?.getBoundingClientRect();
      const sheetStyle = sheetElement ? getComputedStyle(sheetElement) : null;
      return {
        input: {
          left: inputRect.left,
          right: inputRect.right,
          width: inputRect.width,
          paddingLeft: inputStyle.paddingLeft,
          paddingRight: inputStyle.paddingRight,
          boxShadow: inputStyle.boxShadow,
        },
        sheet: sheetRect
          ? {
              left: sheetRect.left,
              right: sheetRect.right,
              width: sheetRect.width,
              overflow: sheetStyle?.overflow,
              paddingLeft: sheetStyle?.paddingLeft,
              paddingRight: sheetStyle?.paddingRight,
            }
          : null,
      };
    });
    const iconIsTopmost = await searchIcon.evaluate((icon) => {
      const rect = icon.getBoundingClientRect();
      const previousPointerEvents = icon.style.pointerEvents;
      icon.style.pointerEvents = 'auto';
      const topElement = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2,
      );
      icon.style.pointerEvents = previousPointerEvents;
      return topElement === icon || icon.contains(topElement);
    });
    console.log(JSON.stringify({ viewport, measurements, iconIsTopmost }));

    await page.screenshot({
      path: testInfo.outputPath(`353-search-${viewport.name}-focused-green.png`),
      fullPage: true,
    });

    expect(measurements.sheet).not.toBeNull();
    if (!measurements.sheet) throw new Error('영양제 추가 시트 경계를 찾지 못했습니다.');
    expect(measurements.input.left - measurements.sheet.left).toBeGreaterThanOrEqual(4);
    expect(measurements.sheet.right - measurements.input.right).toBeGreaterThanOrEqual(4);
    expect(measurements.input.boxShadow).toContain('0px 0px 0px 2px');
    expect(iconIsTopmost).toBe(true);

    const inputBox = await search.boundingBox();
    const iconBox = await searchIcon.boundingBox();
    expect(inputBox).not.toBeNull();
    expect(iconBox).not.toBeNull();
    if (!inputBox || !iconBox) throw new Error('검색창 또는 검색 아이콘 경계를 찾지 못했습니다.');
    expect(iconBox.x).toBeGreaterThanOrEqual(inputBox.x + 12);
    expect(iconBox.x + iconBox.width).toBeLessThanOrEqual(inputBox.x + 40);
  });
}

test('검색어와 native clear 타입을 유지한 채 직접 입력을 왕복한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).last().click();

  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  const search = sheet.getByRole('searchbox', { name: '영양제 제품 검색' });
  await search.fill('센트룸');
  await expect(search).toHaveAttribute('type', 'search');

  await sheet.getByRole('button', { name: '직접 입력', exact: true }).click();
  const manualName = sheet.getByRole('textbox', { name: '직접 입력 제품명' });
  await manualName.fill('직접 입력 영양제');
  await sheet.getByRole('button', { name: '검색으로 돌아가기' }).click();

  await expect(search).toHaveValue('센트룸');
  await expect(manualName).toHaveCount(0);
});

test('검색창에서 고른 표준 제품을 기존 추가 흐름으로 저장한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).last().click();

  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('센트룸 실버 우먼');
  const product = sheet.getByRole('listitem').filter({ hasText: '센트룸 실버 우먼' });
  await product.getByRole('button', { name: /센트룸 실버 우먼/ }).click();
  await product.getByRole('button', { name: '추가하기' }).click();

  await expect(sheet).toHaveCount(0);
  await expect(
    page
      .getByRole('region', { name: '먹고 있는 영양제' })
      .getByRole('button', { name: /센트룸 실버 우먼/ }),
  ).toBeVisible();
});

test('직접 입력 제품을 기존 추가 흐름으로 저장한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).last().click();

  const sheet = page.getByRole('dialog', { name: '영양제 추가' });
  await sheet.getByRole('button', { name: '직접 입력', exact: true }).click();
  await sheet.getByRole('textbox', { name: '직접 입력 제품명' }).fill('레이아웃 회귀 영양제');
  await sheet.getByRole('button', { name: '추가하기' }).click();

  await expect(sheet).toHaveCount(0);
  await expect(
    page
      .getByRole('region', { name: '먹고 있는 영양제' })
      .getByRole('button', { name: /레이아웃 회귀 영양제/ }),
  ).toBeVisible();
});
