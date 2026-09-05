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

async function routeHome(page: Page) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'home-compression-token');
    window.sessionStorage.setItem('poke.account-principal', 'home-compression@example.com');
  });
  await page.route('**/api/v1/medications/doses*', (route) => fulfillJson(route, []));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, (route) =>
    fulfillJson(route, MEDICATION_OVERVIEWS),
  );
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
}

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

test('처방이 3개 이상이면 두 행만 먼저 보여주고 접힌 처방은 기록하지 않는다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  await expect(detail.getByRole('article')).toHaveCount(2);
  await expect(detail.getByRole('heading', { name: '8월 25일 처방', exact: true })).toHaveCount(0);
  const expandOthers = detail.getByRole('button', { name: '다른 처방 펼치기' });
  await expect(expandOthers).toBeVisible();
  await expect(expandOthers).toHaveCSS('font-size', '11px');
  await expect(expandOthers).toHaveCSS('font-weight', '500');
  await expect(expandOthers).toHaveAttribute('aria-expanded', 'false');
  const collapsedWidth = (await detail.boundingBox())!.width;
  await expandOthers.click();
  await expect(detail.getByRole('article')).toHaveCount(3);
  await expect(detail.getByRole('heading', { name: '8월 25일 처방', exact: true })).toBeVisible();
  const thirdEpisode = detail.getByRole('article').nth(2);
  const thirdSelector = thirdEpisode.getByRole('button', { name: '8월 25일 처방 선택' });
  await thirdSelector.click();
  await expect(thirdSelector).toHaveAttribute('aria-pressed', 'true');
  const collapseOthers = detail.getByRole('button', { name: '다른 처방 접기', exact: true });
  await expect(collapseOthers).toHaveCount(1);
  await expect(collapseOthers).toHaveAttribute('aria-expanded', 'true');
  expect((await detail.boundingBox())!.width).toBe(collapsedWidth);
  expect(await detail.evaluate((element) => element.scrollWidth)).toBe(
    await detail.evaluate((element) => element.clientWidth),
  );
  await collapseOthers.click();

  const action = detail.getByRole('button', { name: '먹었어요' });
  await action.click();
  await expect(detail.getByRole('article').nth(0).getByText('복용 완료')).toBeVisible();
  await expect(detail.getByRole('article').nth(1).getByText('복용 완료')).toBeVisible();
  await expect(detail.getByRole('article').nth(2)).toHaveCount(0);
  await detail.getByRole('button', { name: '다른 처방 펼치기' }).click();
  const hiddenEpisode = detail.getByRole('article').nth(2);
  await expect(hiddenEpisode.getByRole('heading', { name: '8월 25일 처방', exact: true })).toBeVisible();
  await expect(hiddenEpisode.getByText('복용 완료', { exact: true })).toHaveCount(0);
  await expect(hiddenEpisode.getByRole('button', { name: '8월 25일 처방 선택' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
});

test('처방 별칭은 화면 제목에만 사용하고 날짜 기반 접근성 이름을 유지한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const first = detail.getByRole('article', { name: /8월 22일 처방/ });
  await expect(first.getByRole('heading', { name: '첫 처방', exact: true })).toBeVisible();
  await expect(first.locator('[data-episode-row]')).toHaveAccessibleName('8월 22일 처방 선택');
  await expect(
    first.getByRole('button', { name: '8월 22일 처방 펼치기', exact: true }),
  ).toBeVisible();
});

test('펼친 처방의 약은 세 개까지 보이고 남은 약을 별도로 펼친다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const detail = page.getByRole('region', { name: '오늘의 복약' }).getByRole('group', {
    name: '아침약 상세',
  });
  const first = detail.getByRole('article').first();
  await first.getByRole('button', { name: /8월 22일 처방.*펼치기/ }).click();
  const medicationList = first.getByRole('list', { name: '8월 22일 처방 약 목록' });
  await expect(medicationList.getByRole('listitem')).toHaveCount(3);
  await expect(first.getByText('8월 22일 처방', { exact: true })).toHaveCount(1);
  await expect(medicationList.getByText(/처방/)).toHaveCount(0);
  const more = first.getByRole('button', { name: '약 2개 더보기' });
  await expect(more).toBeVisible();
  await expect(more).toHaveCSS('font-size', '11px');
  await expect(more).toHaveCSS('font-weight', '500');
  await expect(more).toHaveAttribute('aria-expanded', 'false');
  await more.click();
  await expect(medicationList.getByRole('listitem')).toHaveCount(5);
  const medicationCollapse = first.getByRole('button', { name: '약 목록 접기', exact: true });
  await expect(medicationCollapse).toHaveCount(1);
  await expect(medicationCollapse).toHaveAttribute('aria-expanded', 'true');
  await expect(medicationCollapse).toHaveText('');
  await expect(medicationCollapse.locator('svg')).toHaveCount(1);
  await medicationCollapse.click();
  await expect(medicationList.getByRole('listitem')).toHaveCount(3);
  await expect(first.getByRole('button', { name: '약 2개 더보기' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
});

test('처방 상세 화살표는 약 목록을 펼쳐도 같은 자리에 유지된다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await routeHome(page);
  await page.goto('/home');

  const first = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('article', { name: /8월 22일 처방/ });
  const expand = first.getByRole('button', { name: '8월 22일 처방 펼치기', exact: true });
  const before = await expand.boundingBox();
  expect(before).not.toBeNull();
  await expand.click();
  const collapse = first.getByRole('button', { name: '8월 22일 처방 접기', exact: true });
  const after = await collapse.boundingBox();
  expect(after).not.toBeNull();

  expect(after!.x).toBe(before!.x);
  expect(after!.y).toBe(before!.y);
});
