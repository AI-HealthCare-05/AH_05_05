import { expect, test, type Locator, type Page } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(30_000);
test.use({ reducedMotion: 'reduce' });
const today = '2026-09-15';

async function waitForScrollEnd(viewport: Locator, before: number) {
  await expect.poll(() => viewport.evaluate(element => element.scrollLeft)).not.toBe(before);
  let previous = -1;
  let stable = 0;
  await expect.poll(async () => {
    const current = await viewport.evaluate(element => element.scrollLeft);
    stable = Math.abs(current - previous) < 1 ? stable + 1 : 0;
    previous = current;
    return stable;
  }, { intervals: [50] }).toBeGreaterThanOrEqual(3);
}

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
  await page.setViewportSize({ width: 390, height: 1100 });
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

test('오늘 복약 목표가 없어도 활성 참여 4개가 홈에 표시되고 마지막 카드까지 이동한다', async ({ page }, testInfo) => {
  const medication = custom(701, 'MEDICATION', {
    occurrences: [{ id: 701, targetId: 701, scheduledDate: '2026-09-16', slot: 'MORNING',
      scheduledAt: '2026-09-16T08:00:00+09:00', isCompleted: false }],
  });
  await stub(page, [medication, custom(702), custom(703)]);
  const writes: string[] = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/') && request.method() !== 'GET') writes.push(request.url());
  });
  await page.goto('/home');
  const summary = page.getByRole('region', { name: '챌린지', exact: true });
  await expect(summary.getByRole('article')).toHaveCount(4);
  const medicationCard = summary.getByRole('article', { name: '복약 챌린지', exact: true });
  await expect(medicationCard).toContainText('오늘 예정 없음');
  await expect(medicationCard.getByText('완료', { exact: true })).toHaveCount(0);
  await expect(medicationCard.getByRole('button')).toHaveCount(0);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await summary.scrollIntoViewIfNeeded();
    const next = summary.getByRole('button', { name: '다음 챌린지' });
    await expect(next).toBeEnabled();
    const viewport = summary.getByLabel('오늘 할 챌린지', { exact: true });
    for (let index = 0; index < 4; index++) {
      const { before, max } = await viewport.evaluate(element => ({ before: element.scrollLeft, max: element.scrollWidth - element.clientWidth }));
      if (before >= max - 2) break;
      await next.click();
      await waitForScrollEnd(viewport, before);
    }
    const last = summary.locator('a[href="/challenges/custom-participations/703"]');
    await page.screenshot({ path: testInfo.outputPath(`home-scroll-${width}.png`), fullPage: true });
    await expect(last).toBeInViewport({ ratio: 1 });
    await expect(next).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`home-last-${width}.png`), fullPage: true });
    const previous = summary.getByRole('button', { name: '이전 챌린지' });
    for (let index = 0; index < 4; index++) {
      const before = await viewport.evaluate(element => element.scrollLeft);
      if (before <= 2) break;
      await previous.click();
      await waitForScrollEnd(viewport, before);
    }
    await expect(summary.getByRole('button', { name: '스트레칭 챌린지 했어요' })).toBeEnabled();
    await page.screenshot({ path: testInfo.outputPath(`home-first-${width}.png`), fullPage: true });
  }
  await page.reload();
  await expect(summary.getByRole('article')).toHaveCount(4);
  expect(writes).toEqual([]);
});

test('목표 0건은 완료가 아니며 오늘 끝난 참여만 유지하고 취소·만료·과거 완료는 제외한다', async ({ page }) => {
  const items = [
    custom(701, 'MEDICATION', { occurrences: [], targetDayCount: 0, completedDayCount: 0, dayProgressRate: '0' }),
    custom(702, 'SUPPLEMENT', { status: 'COMPLETED', occurrences: [{ id: 702, targetId: 702,
      scheduledDate: today, slot: 'MORNING', scheduledAt: `${today}T08:00:00+09:00`, isCompleted: true }] }),
    custom(703, 'SUPPLEMENT', { status: 'CANCELLED' }),
    custom(704, 'SUPPLEMENT', { status: 'EXPIRED' }),
    custom(705, 'SUPPLEMENT', { status: 'COMPLETED', occurrences: [] }),
  ];
  await stub(page, items, []);
  await page.goto('/home');
  const summary = page.getByRole('region', { name: '챌린지', exact: true });
  await expect(summary.getByRole('article')).toHaveCount(2);
  const zero = summary.getByRole('article', { name: '복약 챌린지' });
  await expect(zero).toContainText('0 / 0일');
  await expect(zero).toContainText('오늘 예정 없음');
  await expect(zero.getByText('완료', { exact: true })).toHaveCount(0);
  await expect(summary.getByRole('article', { name: '영양제 챌린지' }).getByText('완료', { exact: true })).toBeVisible();
});

test('공식 참여는 오늘 인증 불가여도 홈에서 상세를 열 수 있고 인증 버튼은 제공하지 않는다', async ({ page }) => {
  await stub(page, [], [{ ...official, can_verify: false }]);
  await page.goto('/home');
  const card = page.getByRole('region', { name: '챌린지', exact: true }).getByRole('article', { name: '스트레칭 챌린지' });
  await expect(card.getByRole('link')).toHaveAttribute('href', '/challenges/participations/501');
  await expect(card.getByRole('button')).toHaveCount(0);
  await expect(card.getByText('완료', { exact: true })).toHaveCount(0);
});
