import { expect, test, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(30_000);
test.use({ reducedMotion: 'reduce' });
const today = '2026-09-15';
const official = {
  id: 501, user_id: 7, challenge_id: 101, challenge_name: '스트레칭 챌린지',
  status: 'ACTIVE', joined_at: '2026-09-13T09:00:00+09:00',
  started_at: '2026-09-13T00:00:00+09:00', end_at: '2026-09-20T00:00:00+09:00',
  target_count: 7, completed_count: 2, progress_rate: '28.57',
  completed_at: null, cancelled_at: null, progress_periods: [],
  today, today_verification: null, can_verify: true, verified_dates: ['2026-09-13', '2026-09-14'],
  challenge: {
    id: 101, name: '스트레칭 챌린지', phrase: '하루 한 번 스트레칭', description: null,
    challenge_type_code: 'OFFICIAL', period_code: 'D7', duration_days: 7,
    check_type_code: 'SELF', frequency_code: 'DAILY',
    recruit_start_at: '2026-09-01T00:00:00+09:00', recruit_end_at: '2026-09-30T23:59:59+09:00',
    reward_badge: null, can_join: false, participation_id: 501,
  },
};

function custom(id: number, challengeType = 'SUPPLEMENT', overrides: Record<string, unknown> = {}) {
  return {
    id, templateId: 31, challengeType,
    challengeName: challengeType === 'MEDICATION' ? '복약 챌린지' : '영양제 챌린지',
    rewardBadge: null, status: 'ACTIVE', joinedAt: '2026-09-13T09:00:00+09:00',
    endAt: '2026-09-20T00:00:00+09:00', actualEndDate: '2026-09-19',
    targetCount: 7, completedCount: 1, progressRate: '14.29',
    targetDayCount: 7, completedDayCount: 1, dayProgressRate: '14.29', action: 'NONE',
    targets: [{ id, sourceId: id, name: challengeType === 'MEDICATION' ? '한빛피부과의원' : `영양제 ${id}` }],
    occurrences: [{ id, targetId: id, scheduledDate: today, slot: 'EVENING',
      scheduledAt: `${today}T18:00:00+09:00`, isCompleted: false }],
    ...overrides,
  };
}

async function stub(page: Page, customs: ReturnType<typeof custom>[], officials = [official]) {
  page.on('pageerror', error => console.error(error));
  await page.clock.setFixedTime(new Date(`${today}T12:00:00+09:00`));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-500-test');
    sessionStorage.setItem('poke.account-principal', 'feature-500');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: officials, total_count: officials.length } }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: customs, totalCount: customs.length } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: { items: [], totalCount: 0 } }));
  await page.route('**/api/v1/medications*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/supplement-doses*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/user-suppl-nutr*', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null } }));
  await page.route('**/api/v1/display/med/nutr/rank*', route => route.fulfill({ status: 204 }));
}

test('목록은 공식·복약·영양제 퍼센트 문구 없이 일수와 진행 막대를 유지한다', async ({ page }, testInfo) => {
  await stub(page, [custom(701, 'MEDICATION'), custom(702)]);
  await page.goto('/challenges');
  await page.getByRole('button', { name: '진행 중인 챌린지 펼치기' }).click();
  for (const [name, count, rate] of [
    ['스트레칭 챌린지', '2 / 7일 인증', '28.57'],
    ['복약 챌린지', '1 / 7일', '14.29'],
    ['영양제 챌린지', '1 / 7일', '14.29'],
  ]) {
    const card = page.getByRole('article', { name, exact: true });
    await expect(card).toContainText(count);
    await expect(card).not.toContainText('%');
    await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow', rate);
    await expect(card.getByRole('link')).toHaveAttribute('href', /participations\/\d+$/);
  }
  await expect(page.getByRole('button', { name: '했어요', exact: true })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('challenge-list.png'), fullPage: true });
});

test('지난 기록의 퍼센트도 숨기고 달성·취소·종료 상태는 보존한다', async ({ page }) => {
  await stub(page, ['COMPLETED', 'CANCELLED', 'EXPIRED'].map((status, index) => custom(701 + index, 'MEDICATION', { status })), []);
  await page.goto('/challenges');
  await page.getByRole('button', { name: /지난 기록/ }).click();
  const cards = page.getByRole('article', { name: '복약 챌린지', exact: true });
  await expect(cards).toHaveCount(3);
  for (const [index, status] of ['달성', '취소', '종료'].entries()) {
    await expect(cards.nth(index)).toContainText(status);
    await expect(cards.nth(index)).not.toContainText('%');
  }
});
