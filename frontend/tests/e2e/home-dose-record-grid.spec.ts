import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON, REAL_API_ONLY_REASON } from './helpers/mode';

async function expandMorningMedication(page: Page) {
  await expect(
    page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', { name: '아침약 상세' }),
  ).toBeVisible();
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

test('400일 전 ACTIVE 회차는 from을 처방 시작일로 유지한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'home-range-token');
    window.sessionStorage.setItem('poke.account-principal', 'home-range@example.com');
  });
  const ranges: URL[] = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    ranges.push(new URL(route.request().url()));
    await fulfillJson(route, []);
  });
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [
    {
      recordId: 400, documentImageUrl: '/mock/medication-envelope.svg',
      start: { date: '2025-07-21', slot: 'morning' }, endDate: '2025-08-10', daysRemaining: 0,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
      medications: [{ medicationId: 400, name: '지난 처방', dose: '1정', days: 21, daysRemaining: 0, slots: ['morning'], asNeeded: false }],
    },
  ]));

  await page.goto('/home');
  await expect(page.getByRole('region', { name: '복약 기록' })).toBeVisible();
  expect(ranges).toHaveLength(1);
  expect(ranges[0].searchParams.get('from')).toBe('2025-07-21');
  expect(ranges[0].searchParams.get('to')).toBe('2025-08-10');
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toHaveCount(0);
});

test('365일 처방과 새 30일 회차는 정확히 366일 범위로 복약 기록을 조회한다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'home-range-token');
    window.sessionStorage.setItem('poke.account-principal', 'home-range@example.com');
  });
  const ranges: URL[] = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    ranges.push(new URL(route.request().url()));
    await fulfillJson(route, []);
  });
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [
    {
      recordId: 365, documentImageUrl: '/mock/medication-envelope.svg',
      start: { date: '2025-08-25', slot: 'morning' }, endDate: '2026-08-24', daysRemaining: 0,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
      medications: [{ medicationId: 365, name: '365일 처방', dose: '1정', days: 365, daysRemaining: 0, slots: ['morning'], asNeeded: false }],
    },
    {
      recordId: 366, documentImageUrl: '/mock/medication-envelope.svg',
      start: { date: '2026-08-25', slot: 'morning' }, endDate: '2026-09-23', daysRemaining: 30,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
      medications: [{ medicationId: 366, name: '새 처방', dose: '1정', days: 30, daysRemaining: 30, slots: ['morning'], asNeeded: false }],
    },
  ]));

  await page.goto('/home');
  await expect(page.getByRole('region', { name: '복약 기록' })).toBeVisible();
  expect(ranges).toHaveLength(1);
  expect(ranges[0].searchParams.get('from')).toBe('2025-09-23');
  expect(ranges[0].searchParams.get('to')).toBe('2026-09-23');
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toHaveCount(0);
});
test('다중 care episode 목업은 서로 다른 회차를 같은 복약 카드에 제공한다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-multiple-episodes');

  const morning = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await expect(page.getByText('셀레콕시브 200mg')).toHaveCount(0);
  await expect(page.getByText('아목시실린 500mg')).toHaveCount(0);

  await morning.getByRole('article', { name: /8월 22일 처방/ }).getByRole('button', { name: /펼치기/ }).click();
  await expect(
    morning.getByRole('article', { name: /8월 22일 처방/ })
      .getByRole('group', { name: /처방 약 상세/ })
      .getByText('셀레콕시브 200mg', { exact: true }),
  ).toBeVisible();
  await morning.getByRole('article', { name: /8월 24일 처방/ }).getByRole('button', { name: /펼치기/ }).click();
  await expect(
    morning.getByRole('article', { name: /8월 24일 처방/ })
      .getByRole('list', { name: /처방 약 목록/ })
      .getByText('아목시실린 500mg', { exact: true }),
  ).toBeVisible();
  await expect(morning.getByRole('heading', { name: '8월 22일 처방', exact: true })).toHaveCount(1);
  await expect(
    morning.getByRole('heading', { name: '8월 24일 처방', exact: true }),
  ).toBeVisible();

  await morning.getByRole('button', { name: '3개 먹었어요' }).click();
  await expect(page.getByLabel('8월 25일 아침 먹은 기록')).toBeVisible();

  await morning.getByRole('article', { name: /8월 22일 처방/ }).getByRole('button', { name: /접기/ }).click();
  await expect(page.getByText('셀레콕시브 200mg')).toHaveCount(0);
});

test('홈 잔디는 타임라인 아래에서 복약 기간과 약이 있는 슬롯만 보여준다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const timeline = page.getByRole('region', { name: '오늘의 복약' });
  const records = page.getByRole('region', { name: '복약 기록' });

  await expect(records.getByText('8월 22일 ~ 31일')).toBeVisible();
  await expect(records.getByRole('columnheader')).toHaveCount(10);
  await expect(records.getByRole('row', { name: '아침' })).toBeVisible();
  await expect(records.getByRole('row', { name: '저녁' })).toBeVisible();
  await expect(records.getByRole('row', { name: '점심' })).toHaveCount(0);
  await expect(records.getByRole('row', { name: '취침 전' })).toHaveCount(0);
  await expect(records.getByLabel('8월 22일 아침 먹은 기록')).toBeVisible();
  await expect(records.getByLabel('8월 25일 아침 기록 없음')).toBeVisible();
  await expect(records.getByLabel('8월 25일 저녁 아직')).toBeVisible();
  await expect(records.getByLabel('8월 29일 아침 약 없음')).toBeVisible();
  await expect(records.getByLabel('8월 29일 저녁 아직')).toBeVisible();
  await expect(records.getByText('먹은 기록', { exact: true })).toBeVisible();
  await expect(records.getByText('기록 없음', { exact: true })).toBeVisible();
  await expect(records.getByText('아직', { exact: true })).toBeVisible();
  await expect(records.getByText(/안 먹음|안 드셨어요|%|연속/)).toHaveCount(0);

  await expect(records.getByRole('button', { name: '이전 10일' })).toBeDisabled();
  await expect(records.getByRole('button', { name: '다음 10일' })).toBeDisabled();

  const timelineBox = await timeline.boundingBox();
  const recordsBox = await records.boundingBox();
  expect(timelineBox).not.toBeNull();
  expect(recordsBox).not.toBeNull();
  expect(timelineBox!.y + timelineBox!.height).toBeLessThanOrEqual(recordsBox!.y);
});

test('홈에서 먹었어요를 누르면 오늘 잔디 칸이 새로고침 없이 채워지고 되돌릴 수 있다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');

  await expandMorningMedication(page);
  await page.getByRole('button', { name: '2개 먹었어요' }).click();
  await expect(page.getByLabel('8월 25일 아침 먹은 기록')).toBeVisible();
  await page.getByRole('button', { name: '되돌리기' }).click();
  await expect(page.getByLabel('8월 25일 아침 기록 없음')).toBeVisible();
});

test('지난 기록 없음 칸은 뒤늦게 체크되고 아직 칸은 반응하지 않는다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-active');
  const past = page.getByLabel('8월 24일 저녁 기록 없음');
  const future = page.getByLabel('8월 25일 저녁 아직');

  await expect(future).toBeDisabled();
  await past.click();
  await expect(page.getByLabel('8월 24일 저녁 먹은 기록')).toBeVisible();
});

test('14일 복약 기록은 375px 홈에서 10일씩 이동하며 가로 스크롤이 생기지 않는다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-14-days');
  const grid = page.getByRole('grid', { name: '복약 기간 기록' });
  const previous = page.getByRole('button', { name: '이전 10일' });
  const next = page.getByRole('button', { name: '다음 10일' });

  await expect(page.getByText('8월 22일 ~ 31일')).toBeVisible();
  await expect(grid.getByRole('columnheader')).toHaveCount(10);
  await expect(previous).toBeDisabled();
  await expect(next).toBeEnabled();
  const overflow = await grid.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
  const viewportOverflow = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewportOverflow.scrollWidth).toBeLessThanOrEqual(viewportOverflow.clientWidth);

  await next.click();
  await expect(page.getByText('9월 1일 ~ 4일')).toBeVisible();
  await expect(grid.getByRole('columnheader')).toHaveCount(4);
  await expect(page.getByLabel('9월 1일 아침 아직')).toBeVisible();
  await expect(page.getByLabel('8월 22일 아침 먹은 기록')).toHaveCount(0);
  await expect(previous).toBeEnabled();
  await expect(next).toBeDisabled();
});

test('480px에서도 슬롯명과 첫 날짜 사이가 목업 간격을 유지한다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.setViewportSize({ width: 480, height: 812 });
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/home-14-days');

  const rowHeader = page.getByRole('rowheader', { name: '아침' });
  const rowHeaderTextRight = await rowHeader.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const box = range.getBoundingClientRect();
    return box.x + box.width;
  });
  const firstDateBox = await page
    .getByRole('columnheader', { name: '8월 22일' })
    .boundingBox();

  expect(firstDateBox).not.toBeNull();
  const labelToFirstDateGap = firstDateBox!.x - rowHeaderTextRight;
  expect(labelToFirstDateGap).toBeGreaterThanOrEqual(0);
  expect(labelToFirstDateGap).toBeLessThanOrEqual(24);
});

test('복약 기록의 기간 이동과 과거 기록 셀은 375·390px에서 44px 터치 영역을 제공한다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);

  for (const viewport of [
    { width: 375, height: 812 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
    await page.goto('/dev/home-14-days');

    const tabbarBox = await page.getByRole('navigation', { name: '주요 화면' }).boundingBox();
    expect(tabbarBox?.height, `tabbar height at ${viewport.width}px`).toBe(64);

    const grid = page.getByRole('grid', { name: '복약 기간 기록' });
    for (const label of ['이전 10일', '다음 10일']) {
      const box = await page.getByRole('button', { name: label }).boundingBox();
      expect(box?.width, `${label} width at ${viewport.width}px`).toBeGreaterThanOrEqual(44);
      expect(box?.height, `${label} height at ${viewport.width}px`).toBeGreaterThanOrEqual(44);
    }

    const interactiveCells = grid.locator('button[role="gridcell"]');
    const cellBoxes = await interactiveCells.evaluateAll((elements) =>
      elements.map((element) => {
        const { width, height } = element.getBoundingClientRect();
        return { width, height };
      }),
    );
    expect(cellBoxes.length).toBeGreaterThan(0);
    for (const box of cellBoxes) {
      expect(box.width).toBeGreaterThanOrEqual(44);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }
    const visualBoxes = await interactiveCells
      .locator('[data-record-cell-visual]')
      .evaluateAll((elements) =>
        elements.map((element) => {
          const { width, height } = element.getBoundingClientRect();
          return { width, height };
        }),
      );
    expect(visualBoxes.length).toBe(cellBoxes.length);
    for (const box of visualBoxes) {
      expect(box.width).toBeLessThanOrEqual(30);
      expect(box.height).toBeLessThanOrEqual(22);
    }

    const overflow = await page.evaluate(() => ({
      viewportWidth: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      mainWidth: document.querySelector('main')?.scrollWidth ?? 0,
    }));
    expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth);
    expect(overflow.mainWidth).toBeLessThanOrEqual(overflow.viewportWidth);
  }
});

test('복약이 끝난 홈에도 그 회차의 기록 잔디가 남고 복약 탭에는 중복하지 않는다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-01T12:00:00+09:00'));
  await page.goto('/dev/home-data-ended');
  await expect(page.getByRole('region', { name: '복약 기록' })).toBeVisible();

  await page.goto('/dev/medications');
  await expect(page.getByRole('region', { name: '복약 기록' })).toHaveCount(0);
});
