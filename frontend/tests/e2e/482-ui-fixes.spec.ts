import { expect, test, type Locator, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

const TODAY = '2026-09-02';

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date(`${TODAY}T12:00:00+09:00`));
});

async function openCustomPeriod(page: Page) {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: '최근 6개월' }).click();
  const sheet = page.getByRole('dialog', { name: '조회 기간' });
  await sheet.getByText('직접 지정', { exact: true }).click();
  return sheet;
}

async function box(locator: Locator) {
  const bounds = await locator.boundingBox();
  expect(bounds).not.toBeNull();
  return bounds!;
}

test('필터 전용 달력은 입력 위에서 날짜를 선택하고 적용한 범위를 다시 연다', async ({ page }) => {
  const sheet = await openCustomPeriod(page);
  const from = sheet.getByLabel('시작일', { exact: true });

  await expect(from).toHaveAttribute('type', 'text');
  await expect(from).toHaveAttribute('inputmode', 'numeric');
  await from.click();
  await expect(sheet.getByRole('region', { name: '시작일 달력' })).toHaveCount(0);

  const opener = sheet.getByRole('button', { name: '시작일 달력 열기' });
  await opener.click();
  const calendar = sheet.getByRole('region', { name: '시작일 달력' });
  await expect(calendar).toBeVisible();
  expect(
    await calendar.evaluate((node, input) =>
      Boolean(node.compareDocumentPosition(input as Node) & Node.DOCUMENT_POSITION_FOLLOWING),
    await from.elementHandle()),
  ).toBe(true);
  expect((await box(calendar)).y + (await box(calendar)).height).toBeLessThanOrEqual((await box(from)).y);

  await calendar.getByRole('button', { name: '2026년 9월 1일', exact: true }).click();
  await expect(from).toHaveValue('2026-09-01');
  await expect(opener).toBeFocused();
  await sheet.getByLabel('종료일', { exact: true }).fill(TODAY);
  await sheet.getByRole('button', { name: '적용', exact: true }).click();
  await expect(page).toHaveURL(/from=2026-09-01&to=2026-09-02/);

  await page.getByRole('button', { name: '직접 지정' }).click();
  await expect(page.getByLabel('시작일', { exact: true })).toHaveValue('2026-09-01');
  await expect(page.getByLabel('종료일', { exact: true })).toHaveValue(TODAY);
});

test('달력은 범위 밖 날짜를 막고 12월에서 다음 해 1월로 이동한다', async ({ page }) => {
  await page.goto('/dev/medications?from=2025-12-31&to=2026-09-02');
  await page.getByRole('button', { name: '직접 지정' }).click();
  const sheet = page.getByRole('dialog', { name: '조회 기간' });
  await sheet.getByRole('button', { name: '시작일 달력 열기' }).click();
  const calendar = sheet.getByRole('region', { name: '시작일 달력' });
  await expect(calendar.getByRole('heading', { name: '2025년 12월' })).toBeVisible();
  await expect(calendar.getByRole('button', { name: '2025년 12월 31일' }))
    .toHaveAttribute('aria-pressed', 'true');
  await calendar.getByRole('button', { name: '다음 달' }).click();
  await expect(calendar.getByRole('heading', { name: '2026년 1월' })).toBeVisible();

  await sheet.getByRole('button', { name: '종료일 달력 열기' }).click();
  const endCalendar = sheet.getByRole('region', { name: '종료일 달력' });
  await expect(endCalendar.getByRole('button', { name: '2026년 9월 3일', exact: true })).toBeDisabled();
});

for (const entry of [
  {
    name: '허용 범위보다 이른 날짜',
    typed: '20230101',
    formatted: '2023-01-01',
    expectedMonth: '2024년 9월',
    selectableDate: '2024년 9월 2일',
  },
  {
    name: '허용 범위보다 늦은 날짜',
    typed: '20270101',
    formatted: '2027-01-01',
    expectedMonth: '2026년 9월',
    selectableDate: '2026년 9월 2일',
  },
]) {
  test(`${entry.name}를 입력해도 달력은 가장 가까운 허용 월에서 복구한다`, async ({ page }) => {
    const sheet = await openCustomPeriod(page);
    const from = sheet.getByLabel('시작일', { exact: true });
    await from.fill(entry.typed);
    await expect(from).toHaveValue(entry.formatted);
    await sheet.getByRole('button', { name: '시작일 달력 열기' }).click();

    const calendar = sheet.getByRole('region', { name: '시작일 달력' });
    await expect(calendar.getByRole('heading', { name: entry.expectedMonth })).toBeVisible();
    await expect(calendar.getByRole('button', { name: entry.selectableDate, exact: true })).toBeEnabled();
    await expect(from).toHaveValue(entry.formatted);
  });
}

test('직접 입력은 엄격한 ISO 날짜 형식을 검증한다', async ({ page }) => {
  const sheet = await openCustomPeriod(page);
  const from = sheet.getByLabel('시작일', { exact: true });
  await from.fill('20261340');
  await expect(from).toHaveValue('2026-13-40');
  await sheet.getByLabel('종료일', { exact: true }).fill(TODAY);
  await sheet.getByRole('button', { name: '적용', exact: true }).click();
  await expect(sheet).toContainText('날짜는 YYYY-MM-DD 형식으로 입력해주세요.');
  await expect(page).toHaveURL(/\/dev\/medications$/);
});

for (const viewport of [
  { width: 320, height: 568 },
  { width: 390, height: 844 },
  { width: 844, height: 390 },
]) {
  test(`${viewport.width}x${viewport.height}에서 달력과 입력은 스크롤 가능한 시트 안에 머문다`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const sheet = await openCustomPeriod(page);
    await sheet.getByRole('button', { name: '시작일 달력 열기' }).click();
    const calendar = sheet.getByRole('region', { name: '시작일 달력' });
    const from = sheet.getByLabel('시작일', { exact: true });
    await expect(calendar).toBeVisible();
    const [initialSheetBox, initialCalendarBox] = await Promise.all([box(sheet), box(calendar)]);
    expect(initialCalendarBox.y).toBeGreaterThanOrEqual(initialSheetBox.y - 1);
    expect(initialCalendarBox.y + initialCalendarBox.height)
      .toBeLessThanOrEqual(initialSheetBox.y + initialSheetBox.height + 1);
    expect((await box(calendar.getByRole('button', { name: '2026년 9월 1일' }))).width)
      .toBeLessThanOrEqual(44);
    await from.scrollIntoViewIfNeeded();

    const metrics = await sheet.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        top: bounds.top,
        bottom: bounds.bottom,
        overflowY: style.overflowY,
        scrollHeight: element.scrollHeight,
        clientHeight: element.clientHeight,
      };
    });
    expect(metrics.top).toBeGreaterThanOrEqual(0);
    expect(metrics.bottom).toBeLessThanOrEqual(viewport.height + 1);
    expect(metrics.overflowY).toMatch(/auto|scroll/);
    if (viewport.height === 390) expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);
    expect((await box(calendar)).y + (await box(calendar)).height).toBeLessThanOrEqual((await box(from)).y);
  });
}

test('영양제 요약 카드는 기록 카드와 같은 둥근 모서리를 유지하며 상세로 이동한다', async ({ page }) => {
  await page.goto('/dev/supplements');
  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /오메가3/ }).click();
  const record = page.getByRole('region', { name: '내 기록' });
  const productInfo = page.getByRole('button', { name: '오메가3 제품 상세정보' });
  const recordCard = record.getByRole('group', { name: '내 메모' });
  const [buttonRadius, cardRadius] = await Promise.all([
    productInfo.evaluate((element) => getComputedStyle(element).borderRadius),
    recordCard.evaluate((element) => getComputedStyle(element).borderRadius),
  ]);
  expect(buttonRadius).toBe(cardRadius);
  expect(Number.parseFloat(buttonRadius)).toBeGreaterThan(0);

  await productInfo.click();
  await expect(page).toHaveURL('/dev/supplements/product/mock-501');
  await expect(page.getByRole('heading', { name: '제품 정보' })).toBeVisible();
});

test('복용 중 개수는 영양제 목록 제목과 같은 글자 크기와 굵기를 사용한다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-482-token');
    sessionStorage.setItem('poke.account-principal', 'feature-482@example.com');
  });
  await page.goto('/medications');
  const count = page.getByRole('region', { name: '복용 중' }).getByText(/^\d+개$/);
  const countStyle = await count.evaluate((element) => {
    const style = getComputedStyle(element);
    return { fontSize: style.fontSize, fontWeight: style.fontWeight };
  });

  await page.goto('/dev/supplements');
  const supplementHeading = page.getByRole('heading', { name: /^영양제 \d+개$/ });
  const headingStyle = await supplementHeading.evaluate((element) => {
    const style = getComputedStyle(element);
    return { fontSize: style.fontSize, fontWeight: style.fontWeight };
  });
  expect(countStyle).toEqual(headingStyle);
});
