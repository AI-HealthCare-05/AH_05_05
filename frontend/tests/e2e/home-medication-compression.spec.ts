import path from 'node:path';
import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const MEDICATION_OVERVIEWS = [
  {
    recordId: 12,
    alias: '첫 처방',
    documentImageUrl: '/mock/medication-envelope.svg',
    start: { date: '2026-08-22', slot: 'morning' },
    endDate: '2026-08-31',
    daysRemaining: 7,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [
      { medicationId: 301, name: '아모잘탄정', dose: '5/50mg · 1정', days: 10, daysRemaining: 7, slots: ['morning'], asNeeded: false },
      { medicationId: 302, name: '가스모틴정', dose: '5mg · 1정', days: 10, daysRemaining: 7, slots: ['morning'], asNeeded: false },
      { medicationId: 303, name: '레바미피드정', dose: '100mg · 1정', days: 10, daysRemaining: 7, slots: ['morning'], asNeeded: false },
      { medicationId: 304, name: '숨은 약 하나', dose: '1정', days: 10, daysRemaining: 7, slots: ['morning'], asNeeded: false },
      { medicationId: 305, name: '숨은 약 둘', dose: '1정', days: 10, daysRemaining: 7, slots: ['morning'], asNeeded: false },
    ],
  },
  {
    recordId: 24,
    alias: '둘째 처방',
    documentImageUrl: '/mock/medication-envelope.svg',
    start: { date: '2026-08-24', slot: 'morning' },
    endDate: '2026-08-31',
    daysRemaining: 7,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [
      { medicationId: 401, name: '두 번째 약', dose: '1정', days: 10, daysRemaining: 7, slots: ['morning'], asNeeded: false },
    ],
  },
  {
    recordId: 36,
    documentImageUrl: '/mock/medication-envelope.svg',
    start: { date: '2026-08-25', slot: 'morning' },
    endDate: '2026-08-31',
    daysRemaining: 7,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [
      { medicationId: 501, name: '세 번째 약', dose: '1정', days: 10, daysRemaining: 7, slots: ['morning'], asNeeded: false },
    ],
  },
];

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function routeHome(page: Page, overviews = MEDICATION_OVERVIEWS) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'home-compression-token');
    window.sessionStorage.setItem('poke.account-principal', 'home-compression@example.com');
  });
  await page.route('**/api/v1/**', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/medications/doses*', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/user/challenges', (route) =>
    fulfillJson(route, { items: [], total_count: 0 }),
  );
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, (route) =>
    fulfillJson(route, overviews),
  );
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/user/custom-challenge-participations*', (route) =>
    fulfillJson(route, { items: [], totalCount: 0 }),
  );
  await page.route(/\/api\/v1\/user\/challenges(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [], totalCount: 0 }),
  );
}

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

test('completion pill stays above the hospital name across widths, expansion, selection and undo', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const overview = { ...MEDICATION_OVERVIEWS[0], alias: '연세봄내과 · 장기 건강 관리 처방' };
  await routeHome(page, [overview]);
  await page.goto('/home');
  const timeline = page.getByRole('region', { name: '오늘의 복약' });
  const detail = page.getByRole('group', { name: '아침약 상세' });
  const row = detail.locator('[data-episode-row]');
  const pill = row.locator('[data-episode-completed-badge]');
  const headerSummary = timeline.locator('[data-medication-completed-summary]');
  await expect(pill).toHaveCount(0);
  await expect(headerSummary).toHaveCount(0);
  await detail.getByRole('button', { name: /처방 펼치기$/ }).click();
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  await row.click();
  await detail.getByRole('button', { name: /먹었어요$/ }).click();
  await expect(row).toHaveAttribute('aria-pressed', 'false');
  await expect(headerSummary).toHaveText('복용 완료');
  await expect(pill).toHaveCount(0);
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    const summaryBox = (await headerSummary.boundingBox())!;
    const titleBox = (await timeline.locator('p').first().boundingBox())!;
    expect(summaryBox.x).toBeGreaterThanOrEqual(titleBox.x + titleBox.width - 1);
    expect(Math.abs(
      summaryBox.y + summaryBox.height / 2 - (titleBox.y + titleBox.height / 2),
    )).toBeLessThanOrEqual(4);
    expect(await detail.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect((await detail.getByRole('button', { name: /처방 접기$/ }).boundingBox())!.width).toBe(44);
    await page.screenshot({ path: testInfo.outputPath(`353-home-medication-completion-${width}.png`), fullPage: true });
  }
  await row.click();
  await expect(row).toHaveAttribute('aria-pressed', 'true');
  await expect(headerSummary).toHaveText('복용 완료');
  await detail.getByRole('button', { name: '복약 기록 되돌리기' }).click();
  await expect(headerSummary).toHaveCount(0);
  await expect(pill).toHaveCount(0);
  await expect(row).toHaveAttribute('aria-pressed', 'false');
});

for (const { hiddenFails, allVisibleTaken } of [
  { hiddenFails: false, allVisibleTaken: false },
  { hiddenFails: true, allVisibleTaken: false },
  { hiddenFails: false, allVisibleTaken: true },
]) {
  test(`collapsed group records hidden incomplete prescriptions and preserves taken ones${hiddenFails ? ' with hidden retry' : allVisibleTaken ? ' when all visible rows are complete' : ''}`, async ({ page }) => {
    test.setTimeout(30_000);
    await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
    await routeHome(page);
    const requests: Array<{ recordId: number; taken: boolean }> = [];
    let failHidden = hiddenFails;
    const records = [{ recordId: 36, date: '2026-08-25', slot: 'morning', taken: true }];
    if (allVisibleTaken) records.push({ recordId: 24, date: '2026-08-25', slot: 'morning', taken: true });
    await page.route('**/api/v1/medications/doses*', async route => {
      if (route.request().method() === 'GET') return fulfillJson(route, records);
      const request = route.request().postDataJSON();
      requests.push(request);
      if (request.recordId === 12 && failHidden) {
        failHidden = false;
        return fulfillJson(route, { message: '잠시 후 다시 시도해주세요' }, 503);
      }
      records.push(request);
      return fulfillJson(route, request);
    });
    await page.goto('/home');
    const detail = page.getByRole('group', { name: '아침약 상세' });
    await expect(detail.getByRole('article')).toHaveCount(2);
    await detail.getByRole('button', { name: /먹었어요$/ }).click();
    await expect.poll(() => requests.map(item => item.recordId).sort()).toEqual(allVisibleTaken ? [12] : [12, 24]);
    expect(requests.every(item => item.taken)).toBe(true);
    if (hiddenFails) {
      await page.getByRole('dialog').getByRole('button', { name: '다시 시도' }).click();
      await expect.poll(() => requests.map(item => item.recordId).sort()).toEqual([12, 12, 24]);
    }
    await detail.getByRole('button', { name: '다른 처방 펼치기' }).click();
    await expect(page.locator('[data-medication-completed-summary]')).toHaveCount(1);
    await expect(detail.locator('[data-episode-completed-badge]')).toHaveCount(0);
    await expect(detail.getByRole('button', { name: '복약 기록 되돌리기' })).toBeDisabled();
    expect(requests.every(item => item.recordId !== 36 && item.taken)).toBe(true);
  });
}

test('오늘의 복약 처방은 기존 순서의 역순으로 표시한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');
  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await expect(detail.getByRole('heading')).toHaveText(['8월 25일 처방', '둘째 처방']);
  await detail.getByRole('button', { name: '다른 처방 펼치기' }).click();
  await expect(detail.getByRole('heading')).toHaveText(['8월 25일 처방', '둘째 처방', '첫 처방']);
  await page.screenshot({ path: 'test-results/home-medication-reverse.png', fullPage: true });
});

test('같은 조제일 처방은 별칭을 접근성 이름에 포함해 서로 구분한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const sameDateOverviews = MEDICATION_OVERVIEWS.slice(0, 2).map((overview) => ({
    ...overview,
    start: { ...overview.start, date: '2026-08-22' },
  }));
  await routeHome(page, sameDateOverviews);
  await page.goto('/home');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await expect(detail.getByRole('button', { name: '첫 처방 · 8월 22일 처방 선택' })).toHaveCount(1);
  await expect(detail.getByRole('button', { name: '둘째 처방 · 8월 22일 처방 선택' })).toHaveCount(1);
  await expect(detail.getByRole('heading')).toHaveText(['둘째 처방', '첫 처방']);
  await expect(detail.getByText('8월 22일 처방', { exact: true })).toHaveCount(0);
});

test('약 이름에 포함된 함량은 펼친 상세에서 반복하지 않는다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const duplicatedStrengthOverviews = MEDICATION_OVERVIEWS.map((overview, overviewIndex) =>
    overviewIndex === 0
      ? {
          ...overview,
          medications: overview.medications.map((medication, medicationIndex) =>
            medicationIndex === 0
              ? { ...medication, name: '아모잘탄정 5/50mg', dose: '5/50mg' }
              : medication,
          ),
        }
      : overview,
  );
  await routeHome(page, duplicatedStrengthOverviews);
  await page.goto('/home');

  await page.getByRole('button', { name: '다른 처방 펼치기' }).click();
  const first = page.getByRole('region', { name: '오늘의 복약' }).getByRole('article', { name: /8월 22일 처방/ });
  await first.getByRole('button', { name: /첫 처방.*펼치기/ }).click();
  await expect(first.getByRole('listitem').first()).toHaveText('아모잘탄정 5/50mg');
});

test('처방이 3개 이상이면 두 행만 먼저 보여줘도 기본 복용은 접힌 처방까지 기록한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await expect(detail.getByRole('article')).toHaveCount(2);
  await expect(detail.getByRole('heading', { name: '첫 처방', exact: true })).toHaveCount(0);
  const expandOthers = detail.getByRole('button', { name: '다른 처방 펼치기' });
  await expect(expandOthers).toBeVisible();
  await expect(expandOthers).toHaveText('펼치기');
  await expect(expandOthers).toHaveCSS('font-size', '11px');
  await expect(expandOthers).toHaveCSS('font-weight', '500');
  await expect(expandOthers).toHaveAttribute('aria-expanded', 'false');
  const collapsedWidth = (await detail.boundingBox())!.width;
  await expandOthers.click();
  await expect(detail.getByRole('article')).toHaveCount(3);
  await expect(detail.getByRole('heading', { name: '첫 처방', exact: true })).toBeVisible();
  const thirdEpisode = detail.getByRole('article').nth(2);
  await thirdEpisode
    .getByRole('button', { name: '첫 처방 · 8월 22일 처방 펼치기', exact: true })
    .click();
  await expect(thirdEpisode.getByText('첫 처방', { exact: true })).toHaveCount(1);
  await expect(
    thirdEpisode.getByRole('list', { name: '8월 22일 처방 약 목록' }).getByText(/처방/),
  ).toHaveCount(0);
  const thirdSelector = thirdEpisode.getByRole('button', { name: '첫 처방 · 8월 22일 처방 선택' });
  await thirdSelector.click();
  await expect(thirdSelector).toHaveAttribute('aria-pressed', 'true');
  const collapseOthers = detail.getByRole('button', { name: '다른 처방 접기', exact: true });
  await expect(collapseOthers).toHaveCount(1);
  await expect(collapseOthers).toHaveText('접기');
  await expect(collapseOthers).toHaveAttribute('aria-expanded', 'true');
  expect((await detail.boundingBox())!.width).toBe(collapsedWidth);
  expect(await detail.evaluate((element) => element.scrollWidth)).toBe(
    await detail.evaluate((element) => element.clientWidth),
  );
  await collapseOthers.click();

  const action = detail.getByRole('button', { name: '먹었어요' });
  await action.click();
  await expect(page.locator('[data-medication-completed-summary]')).toHaveCount(1);
  await expect(detail.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await expect(detail.getByRole('article').nth(2)).toHaveCount(0);
  await detail.getByRole('button', { name: '다른 처방 펼치기' }).click();
  const hiddenEpisode = detail.getByRole('article').nth(2);
  await expect(hiddenEpisode.getByRole('heading', { name: '첫 처방', exact: true })).toBeVisible();
  await expect(hiddenEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await expect(page.locator('[data-medication-completed-summary]')).toHaveText('복용 완료');
  await expect(hiddenEpisode.getByRole('button', { name: '첫 처방 · 8월 22일 처방 복용 완료' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
});

test('처방 별칭은 화면 제목과 날짜 기반 접근성 이름에 함께 사용한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const first = detail.getByRole('article', { name: /8월 22일 처방/ });
  await detail.getByRole('button', { name: '다른 처방 펼치기' }).click();
  await expect(first.getByRole('heading', { name: '첫 처방', exact: true })).toBeVisible();
  await expect(first.locator('[data-episode-row]')).toHaveAccessibleName('첫 처방 · 8월 22일 처방 선택');
  await expect(
    first.getByRole('button', { name: '첫 처방 · 8월 22일 처방 펼치기', exact: true }),
  ).toBeVisible();
});

test('긴 처방 별칭과 약 이름은 모바일과 데스크톱에서 화살표를 고정한 채 전체가 보인다', async ({ page }) => {
  test.setTimeout(120_000);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const longAlias = `퇴원후집중관리처방${'PRESCRIPTION'.repeat(16)}회차`;
  const longMedicationName = `복합성분서방정${'MEDICATION'.repeat(18)}정`;
  const longOverview = [{
    ...MEDICATION_OVERVIEWS[0],
    alias: longAlias,
    medications: [{ ...MEDICATION_OVERVIEWS[0].medications[0], name: longMedicationName }],
  }];
  await routeHome(page, longOverview);

  for (const width of [320, 390, 430, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/home');
    const article = page.getByRole('region', { name: '오늘의 복약' }).getByRole('article');
    const row = article.locator('[data-episode-row]');
    const title = row.getByRole('heading', { name: longAlias, exact: true });
    const summary = row.getByText(longMedicationName, { exact: true });
    const expand = article.getByRole('button', { name: new RegExp(`${longAlias}.*펼치기`) });

    await expect(title).toBeVisible();
    expect(await title.evaluate((element) => getComputedStyle(element).textOverflow)).not.toBe('ellipsis');
    expect(await title.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect(await summary.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect((await row.boundingBox())!.height).toBeGreaterThan(56);
    expect((await row.locator('[data-episode-selection-glyph]').boundingBox())!.width).toBe(24);
    expect((await expand.boundingBox())!.width).toBe(44);

    await expand.click();
    const expandedName = article.getByRole('listitem').getByText(longMedicationName, { exact: true });
    expect(await expandedName.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect(await article.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    await row.click();
    await expect(row).toHaveAttribute('aria-pressed', 'true');
  }
});

test('펼친 처방은 내부 약 목록 토글 없이 모든 약을 표시하고 외부 처방 접기는 유지한다', async ({ page }, testInfo) => {
  test.setTimeout(30_000);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await detail.getByRole('button', { name: '다른 처방 펼치기' }).click();
  const first = detail.getByRole('article', { name: /8월 22일 처방/ });
  await expect(first.getByRole('list')).toHaveCount(0);
  await first.getByRole('button', { name: /8월 22일 처방.*펼치기/ }).click();
  const medicationList = first.getByRole('list', { name: '8월 22일 처방 약 목록' });
  const captureVariant = process.env.CAPTURE_384_VARIANT;
  if (captureVariant === 'before' || captureVariant === 'after') {
    await page.screenshot({
      path: path.resolve(
        testInfo.config.rootDir,
        '../../../design-plans/384/screenshots',
        captureVariant,
        'issue6-expanded-episode-all-medications.png',
      ),
      fullPage: true,
    });
  }
  await expect(medicationList.getByRole('listitem')).toHaveText([
    '아모잘탄정', '가스모틴정', '레바미피드정', '숨은 약 하나', '숨은 약 둘',
  ]);
  await expect(medicationList.getByText(/처방/)).toHaveCount(0);
  await expect(first.getByRole('button', { name: /약 \d+개 더보기|약 목록 접기/ })).toHaveCount(0);
  const collapse = first.getByRole('button', { name: '첫 처방 · 8월 22일 처방 접기', exact: true });
  await expect(collapse).toHaveAttribute('aria-expanded', 'true');
  await collapse.focus();
  await page.keyboard.press('Space');
  await expect(medicationList).toHaveCount(0);
  await expect(first.getByRole('button', { name: '첫 처방 · 8월 22일 처방 펼치기', exact: true })).toHaveAttribute('aria-expanded', 'false');
});

test('네 번째 이후의 긴 약 이름도 한 번의 펼침에서 폭에 맞게 줄바꿈한다', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const longName = `복합서방정${'MEDICATION'.repeat(16)}정`;
  const overview = { ...MEDICATION_OVERVIEWS[0], medications: MEDICATION_OVERVIEWS[0].medications.map(
    (medication, index) => index === 4 ? { ...medication, name: longName } : medication,
  ) };
  await routeHome(page, [overview]);
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/home');
    const episode = page.getByRole('article', { name: '첫 처방 · 8월 22일 처방 · 약 5개', exact: true });
    await episode.getByRole('button', { name: '첫 처방 · 8월 22일 처방 펼치기', exact: true }).click();
    const name = episode.getByRole('listitem').getByText(longName, { exact: true });
    await expect(name).toBeVisible();
    expect(await name.evaluate(element => {
      const style = getComputedStyle(element);
      return element.scrollWidth <= element.clientWidth + 1 && element.scrollHeight <= element.clientHeight + 1
        && style.textOverflow !== 'ellipsis' && style.whiteSpace !== 'nowrap';
    })).toBe(true);
    expect(await episode.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`home-all-drugs-${width}.png`), fullPage: true });
  }
});

test('처방 상세 화살표는 약 목록을 펼쳐도 같은 자리에 유지된다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const first = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('article', { name: /8월 22일 처방/ });
  await page.getByRole('button', { name: '다른 처방 펼치기' }).click();
  const expand = first.getByRole('button', { name: '첫 처방 · 8월 22일 처방 펼치기', exact: true });
  const before = await expand.boundingBox();
  expect(before).not.toBeNull();
  await expand.click();
  const collapse = first.getByRole('button', { name: '첫 처방 · 8월 22일 처방 접기', exact: true });
  const after = await collapse.boundingBox();
  expect(after).not.toBeNull();

  expect(after!.x).toBe(before!.x);
  expect(after!.y).toBe(before!.y);
});
