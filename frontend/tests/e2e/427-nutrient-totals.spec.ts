import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('성분명 옆 합계와 그래프 오른쪽 위의 기존 판정 문구를 표시한다', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  const vitaminA = totals.getByRole('article', { name: '비타민 A 성분 합계' });
  const header = vitaminA.getByTestId('nutrient-total-header');
  const summary = vitaminA.getByTestId('nutrient-total-summary');
  await expect(header).toBeVisible();
  await expect(summary).toContainText('비타민 A');
  await expect(summary).toContainText('3,200');
  await expect(summary).toContainText('µg RAE');
  const nameBox = await vitaminA.getByRole('heading', { name: '비타민 A' }).boundingBox();
  const amountBox = await summary.locator('strong').boundingBox();
  expect(Math.abs((nameBox?.y ?? 0) - (amountBox?.y ?? 0))).toBeLessThan(8);

  const status = vitaminA.getByText('상한 초과', { exact: true });
  const graph = vitaminA.locator('[data-nutrient-range]');
  const upperLimit = vitaminA.locator('[data-threshold="upper-limit"]');
  const statusBox = await status.boundingBox();
  const summaryBox = await summary.boundingBox();
  const headerBox = await header.boundingBox();
  const graphBox = await graph.boundingBox();
  const upperLimitBox = await upperLimit.boundingBox();
  expect(statusBox?.y).toBeLessThan(graphBox?.y ?? 0);
  const statusCenter = (statusBox?.x ?? 0) + (statusBox?.width ?? 0) / 2;
  const upperLimitCenter = (upperLimitBox?.x ?? 0) + (upperLimitBox?.width ?? 0) / 2;
  expect(Math.abs(statusCenter - upperLimitCenter)).toBeLessThanOrEqual(2);
  expect(Math.abs((summaryBox?.y ?? 0) - (statusBox?.y ?? 0))).toBeLessThanOrEqual(8);
  expect((graphBox?.y ?? 0) - ((headerBox?.y ?? 0) + (headerBox?.height ?? 0))).toBeLessThanOrEqual(8);

  const calcium = totals.getByRole('article', { name: '칼슘 성분 합계' });
  await expect(calcium.getByText('권장량의 50%예요', { exact: true })).toBeVisible();
  const vitaminD = totals.getByRole('article', { name: '비타민 D 성분 합계' });
  await expect(vitaminD.getByText('권장 범위예요', { exact: true })).toBeVisible();
});

test('긴 성분명과 전체 판정 문구를 좁은 화면에서 겹치거나 자르지 않는다', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/dev/supplements');

  const calcium = page
    .getByRole('region', { name: '성분 합계' })
    .getByRole('article', { name: '칼슘 성분 합계' });
  const header = calcium.getByTestId('nutrient-total-header');
  const summary = calcium.getByTestId('nutrient-total-summary');
  const status = calcium.getByText('권장량의 50%예요', { exact: true });
  await calcium.getByRole('heading', { name: '칼슘' }).evaluate((element) => {
    element.textContent = '해조칼슘복합추출물유래칼슘';
  });

  await expect(header).toContainText('해조칼슘복합추출물유래칼슘');
  await expect(status).toHaveText('권장량의 50%예요');
  const summaryBox = await summary.boundingBox();
  const statusBox = await status.boundingBox();
  const horizontallySeparated = (summaryBox?.x ?? 0) + (summaryBox?.width ?? 0) <= (statusBox?.x ?? 0);
  const verticallySeparated = (summaryBox?.y ?? 0) + (summaryBox?.height ?? 0) <= (statusBox?.y ?? 0);
  expect(horizontallySeparated || verticallySeparated).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('직접 입력 제품은 목록 배지를 숨기고 성분 합계 제외 안내는 유지한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가', exact: true }).last().click();
  const sheet = page.getByRole('dialog');
  await sheet.getByRole('searchbox', { name: '영양제 제품 검색' }).fill('없는제품-427');
  await sheet.getByRole('button', { name: '직접 입력' }).first().click();
  await sheet.getByRole('textbox', { name: '직접 입력 제품명' }).fill('직접 입력 테스트 영양제');
  await sheet.getByRole('button', { name: '추가하기' }).click();

  const manual = page
    .getByRole('region', { name: '먹고 있는 영양제' })
    .getByRole('button', { name: /직접 입력 테스트 영양제/ });
  await expect(manual).toBeVisible();
  await expect(manual.getByText('성분 정보 없음', { exact: true })).toHaveCount(0);
  await expect(
    page.getByText('직접 입력한 영양제는 성분 합산에 포함되지 않아요.', { exact: true }),
  ).toBeVisible();
});

test('성분 포함 제품을 접어서 제공하고 펼치면 제품명을 모두 보여준다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const vitaminA = page
    .getByRole('region', { name: '성분 합계' })
    .getByRole('article', { name: '비타민 A 성분 합계' });
  const disclosure = vitaminA.getByText('성분 포함 제품 2개', { exact: true });
  await expect(disclosure).toBeVisible();
  await expect(vitaminA.getByText('오메가3', { exact: true })).toBeHidden();
  await disclosure.click();
  await expect(vitaminA.getByText('오메가3', { exact: true })).toBeVisible();
  await expect(vitaminA.getByText('종합비타민', { exact: true })).toBeVisible();
  await expect(vitaminA.getByText(/확인 필요 제품/)).toHaveCount(0);
});

test('기준 정보와 합산 제외 범위를 확정 문구로 안내한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  await expect(
    page.getByText('기준 · 2025 한국인 영양소 섭취기준 · 만 26세 남성', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('검색된 영양제의 성분만 합산된 결과예요.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('직접 입력한 영양제는 성분 합산에 포함되지 않아요.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('음식과 의약품을 통한 섭취량은 포함되지 않아요.', { exact: true }),
  ).toBeVisible();
});

test('자료가 없어 판정할 수 없는 성분에는 상태와 그래프를 만들지 않는다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const selenium = page
    .getByRole('region', { name: '성분 합계' })
    .getByRole('article', { name: '셀레늄 성분 합계' });
  await expect(selenium.getByTestId('nutrient-total-summary')).toContainText('셀레늄');
  await expect(selenium.getByTestId('nutrient-total-summary')).toContainText('55');
  await expect(selenium.getByTestId('nutrient-total-summary')).toContainText('µg');
  await expect(selenium.locator('[data-nutrient-status]')).toHaveCount(0);
  await expect(selenium.locator('[data-nutrient-range]')).toHaveCount(0);
});

test('375px, 390px와 1280px에서 성분 합계가 가로로 넘치지 않는다', async ({ page }, testInfo) => {
  for (const width of [375, 390, 1280]) {
    await page.setViewportSize({ width, height: width === 375 ? 812 : 900 });
    await page.goto('/dev/supplements');
    await expect(page.getByRole('region', { name: '성분 합계' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`nutrient-totals-${width}px.png`),
      fullPage: true,
    });
  }
});
