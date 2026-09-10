import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(60_000);

function participation(type = 'MEDICATION', completeLast = false) {
  return {
    id: 701, templateId: 31, challengeType: type, challengeName: '일수 기준 챌린지',
    rewardBadge: null, status: 'ACTIVE', joinedAt: '2026-09-09T07:00:00+09:00',
    endAt: '2026-09-12T00:00:00+09:00', actualEndDate: '2026-09-11',
    targetCount: 4, completedCount: completeLast ? 4 : 3, progressRate: completeLast ? '100.00' : '75.00',
    action: 'NONE', targets: [{ id: 801, sourceId: 42, name: '맑은비뇨기과의원' }],
    occurrences: [
      ...['MORNING', 'LUNCH', 'EVENING'].map((slot, index) => ({
        id: 901 + index, targetId: 801, scheduledDate: '2026-09-09', slot,
        scheduledAt: `2026-09-09T${['08', '13', '16'][index]}:00:00+09:00`, isCompleted: true,
      })),
      { id: 904, targetId: 801, scheduledDate: '2026-09-11', slot: 'EVENING',
        scheduledAt: '2026-09-11T16:00:00+09:00', isCompleted: completeLast },
    ],
  };
}

async function setup(page: Page, item: ReturnType<typeof participation>) {
  await page.clock.setFixedTime(new Date('2026-09-11T17:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'day-progress-test-token');
    sessionStorage.setItem('poke.account-principal', 'day-progress@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: item }));
  await page.route('**/api/v1/user/custom-challenge-participations/701/claim-reward', route => {
    item.status = 'COMPLETED';
    return route.fulfill({ json: { participation: item, award: null, newlyAwarded: false } });
  });
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [item], totalCount: 1 } }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/medications/doses*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/user-suppl-nutr*', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null } }));
  await page.route('**/api/v1/display/med/nutr/rank*', route => route.fulfill({ status: 204 }));
}

for (const type of ['MEDICATION', 'SUPPLEMENT']) {
  test(`${type}: unequal dose counts count complete days and exclude empty dates`, async ({ page }) => {
    await setup(page, participation(type));
    await page.goto('/challenges/custom-participations/701');
    await expect(page.getByText('1 / 2일', { exact: true })).toBeVisible();
    await expect(page.getByRole('progressbar', { name: '맞춤 챌린지 진행률' })).toHaveAttribute('aria-valuenow', '50');
    await expect(page.getByRole('region', { name: '날짜별 복용 기록' }).getByText('0 / 1회 완료')).toBeVisible();
    await expect(page.getByRole('status').filter({ hasText: '다 먹었어요' })).toHaveCount(0);
  });
}

test('all actual goals done produces days, checked record and filled day', async ({ page }) => {
  await setup(page, participation('MEDICATION', true));
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByText('2 / 2일', { exact: true })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: '맞춤 챌린지 진행률' })).toHaveAttribute('aria-valuenow', '100');
  await expect(page.getByRole('status')).toContainText('오늘 먹을 약을 다 먹었어요!');
  await expect(page.getByRole('button', { name: /2026.09.11, 모두 완료/ }).locator('span')).toHaveClass(/bg-primary/);
});

test('home and my challenges use the same day progress', async ({ page }) => {
  await setup(page, participation());
  await page.goto('/home');
  const home = page.getByRole('link', { name: /일수 기준 챌린지, 50% 진행 중/ });
  await expect(home).toContainText('1 / 2일');
  await page.goto('/challenges');
  await expect(page.getByRole('article', { name: '일수 기준 챌린지' })).toContainText('1 / 2일');
});

test('an incomplete day contributes zero even with two doses done', async ({ page }) => {
  const item = participation();
  item.occurrences[2].isCompleted = false;
  item.completedCount = 2;
  item.progressRate = '50.00';
  await setup(page, item);
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByText('0 / 2일', { exact: true })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: '맞춤 챌린지 진행률' })).toHaveAttribute('aria-valuenow', '0');
});

for (const type of ['MEDICATION', 'SUPPLEMENT']) {
  test(`${type}: refreshed undo clears record, daily completion and day fill together`, async ({ page }) => {
    const item = participation(type, true);
    // Keep a future goal pending: undo is live only before the entire challenge is finalized.
    item.occurrences.push({ id: 905, targetId: 801, scheduledDate: '2026-09-12', slot: 'EVENING', scheduledAt: '2026-09-12T16:00:00+09:00', isCompleted: false });
    const current = Object.assign(item, { endAt: '2026-09-13T00:00:00+09:00', actualEndDate: '2026-09-12', targetCount: 5, progressRate: '80.00', targetDayCount: 3, completedDayCount: 2, dayProgressRate: '66.67' });
    await setup(page, current);
    await page.goto('/challenges/custom-participations/701');
    await expect(page.getByText('2 / 3일', { exact: true })).toBeVisible();
    await expect(page.getByRole('status')).toContainText('다 먹었어요!');
    current.occurrences[3].isCompleted = false;
    current.completedCount = 3;
    current.progressRate = '60.00';
    current.completedDayCount = 1;
    current.dayProgressRate = '33.33';
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(page.getByText('1 / 3일', { exact: true })).toBeVisible();
    await expect(page.getByRole('progressbar', { name: '맞춤 챌린지 진행률' })).toHaveAttribute('aria-valuenow', '33.33');
    await expect(page.getByRole('region', { name: '날짜별 복용 기록' }).getByText('0 / 1회 완료')).toBeVisible();
    await expect(page.getByRole('status').filter({ hasText: '다 먹었어요!' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /2026.09.11, 0\/1 완료/ }).locator('span')).not.toHaveClass(/bg-primary/);
  });
}
