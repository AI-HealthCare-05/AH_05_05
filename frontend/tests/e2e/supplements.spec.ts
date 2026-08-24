import { expect, test } from 'playwright/test';

test('초과 성분을 먼저 보여주고 색 외의 경고와 상한 임계값을 함께 표시한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  const exceeded = totals.getByRole('heading', { name: '비타민 A', exact: true });
  const neutral = totals.getByText('비타민 D', { exact: true });
  await expect(exceeded).toBeVisible();
  await expect(page.getByText('상한 초과', { exact: true })).toBeVisible();
  await expect(page.getByText('3,200', { exact: true })).toBeVisible();
  await expect(page.getByText('상한 3,000', { exact: true })).toBeVisible();
  await expect(neutral).toBeVisible();

  const exceededBox = await exceeded.boundingBox();
  const neutralBox = await neutral.boundingBox();
  expect(exceededBox?.y).toBeLessThan(neutralBox?.y ?? 0);
});

test('영양제 합계의 범위와 기준을 오해하지 않도록 두 고지 문구를 표시한다', async ({ page }) => {
  await page.goto('/dev/supplements');

  await expect(page.getByText('기준 · 2025 한국인 영양소 섭취기준 상한섭취량')).toBeVisible();
  await expect(
    page.getByText(
      '등록한 건강기능식품 3개만 더한 값입니다. 음식과 의약품을 통한 섭취량은 포함되지 않았습니다.',
    ),
  ).toBeVisible();
});

test('영양제 추가는 검색을 기본으로 하고 바코드를 보조 수단으로 제공한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('button', { name: '영양제 추가' }).click();

  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('textbox', { name: '제품 검색' })).toBeVisible();
  await expect(sheet.getByRole('button', { name: '바코드로 찾기' })).toBeVisible();
  await expect(sheet.getByRole('spinbutton', { name: '1일 정수' })).toBeVisible();
  await expect(sheet.getByText('먹는 시간대')).toBeVisible();
});

test('성분 8개에서도 초과 항목을 중립 항목보다 먼저 보여준다', async ({ page }) => {
  await page.goto('/dev/supplements');

  const totals = page.getByRole('region', { name: '성분 합계' });
  await expect(totals.getByRole('article')).toHaveCount(8);
  const exceededBox = await totals.getByRole('article', { name: '비타민 A 성분 합계' }).boundingBox();
  const firstNeutralBox = await totals.getByRole('article', { name: '비타민 D 성분 합계' }).boundingBox();
  expect(exceededBox?.y).toBeLessThan(firstNeutralBox?.y ?? 0);
});

test('상한 초과가 3개여도 모든 경고를 구분하고 가로 넘침이 없다', async ({ page }) => {
  await page.goto('/dev/supplements-three-exceeded');

  await expect(page.getByText('상한 초과', { exact: true })).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
