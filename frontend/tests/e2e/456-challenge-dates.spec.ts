import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

const challenge = {
  id: 456,
  name: '날짜 표시 챌린지',
  phrase: '날짜 형식을 확인해요',
  description: null,
  challenge_type_code: 'OFFICIAL',
  period_code: 'D7',
  duration_days: 7,
  check_type_code: 'SELF',
  frequency_code: 'DAILY',
  recruit_start_at: '2026-08-31T15:30:00Z',
  recruit_end_at: '2026-10-07T23:59:59+09:00',
  reward_badge: null,
  can_join: false,
  participation_id: 501,
};

const officialParticipation = {
  id: 501,
  user_id: 7,
  challenge_id: challenge.id,
  challenge_name: challenge.name,
  status: 'ACTIVE',
  joined_at: '2026-09-30T15:30:00Z',
  started_at: '2026-09-30T15:30:00Z',
  end_at: '2026-10-08T00:00:00+09:00',
  target_count: 7,
  completed_count: 1,
  progress_rate: '14.29',
  completed_at: null,
  cancelled_at: null,
  progress_periods: [{
    id: 801,
    period_start: '2026-10-01',
    period_end: '2026-10-07',
    target_count: 7,
    completed_count: 1,
    progress_rate: '14.29',
    is_completed: false,
    completed_at: null,
  }],
  challenge,
  today: '2026-10-01',
  today_verification: null,
  can_verify: true,
  verified_dates: ['2026-10-01'],
};

const customParticipation = {
  id: 701,
  templateId: 31,
  challengeType: 'MEDICATION',
  challengeName: '맞춤 날짜 챌린지',
  rewardBadge: null,
  status: 'ACTIVE',
  joinedAt: '2026-09-30T15:30:00Z',
  endAt: '2026-10-08T00:00:00+09:00',
  actualEndDate: '2026-10-07',
  targetCount: 7,
  completedCount: 0,
  progressRate: '0.00',
  targetDayCount: 7,
  completedDayCount: 0,
  dayProgressRate: '0.00',
  action: 'NONE',
  targets: [{ id: 901, sourceId: 101, name: '서울의원 처방' }],
  occurrences: [{
    id: 1001,
    targetId: 901,
    scheduledDate: '2026-10-01',
    slot: 'MORNING',
    scheduledAt: '2026-10-01T08:00:00+09:00',
    isCompleted: false,
  }],
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-456-date-token');
    sessionStorage.setItem('poke.account-principal', 'issue-456-dates@example.com');
  });
}

test.beforeEach(async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-10-01T12:00:00+09:00'));
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route =>
    fulfillJson(route, { code: 'FIXTURE_MISSING', message: '456 date fixture missing' }, 503));
});

test('challenge date helpers zero-pad KST dates and keep invalid values safe', async ({ page }) => {
  await page.goto('/');

  const labels = await page.evaluate(async () => {
    const official = await import('/src/pages/challenges/officialChallengeDates.ts');
    const custom = await import('/src/pages/challenges/customChallengeDates.ts');
    return {
      officialBoundary: official.koreanChallengeDate('2026-08-31T15:30:00Z'),
      customBoundary: custom.customChallengeDateLabel('2026-08-31T15:30:00Z'),
      officialInvalid: official.koreanChallengeDate('invalid-date'),
      customInvalid: custom.customChallengeDateLabel('invalid-dateT00:00:00Z'),
      customInvalidDateOnly: custom.customChallengeDateLabel('not-a-date'),
      inclusiveEnd: official.inclusiveChallengeEndDate('2026-10-08T00:00:00+09:00'),
    };
  });

  expect(labels).toEqual({
    officialBoundary: '2026.09.01',
    customBoundary: '2026.09.01',
    officialInvalid: 'invalid-date',
    customInvalid: 'invalid-dateT00:00:00Z',
    customInvalidDateOnly: 'not-a-date',
    inclusiveEnd: '2026-10-07',
  });
});

test('official browse and catalog detail show both full period endpoints', async ({ page }) => {
  await page.route('**/api/v1/user/challenge-catalog?*', route =>
    fulfillJson(route, { items: [challenge], total_count: 1 }));
  await page.route('**/api/v1/user/challenge-catalog/456', route => fulfillJson(route, challenge));
  await page.route('**/api/v1/user/challenges', route =>
    fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route =>
    fulfillJson(route, { items: [], totalCount: 0 }));

  await page.goto('/challenges/browse');
  await page.getByRole('button', { name: '공식 챌린지 펼치기', exact: true }).click();
  await expect(page.getByRole('button', { name: `${challenge.name} 자세히 보기` }))
    .toContainText('모집기간 : 2026.09.01 ~ 2026.10.07');

  await page.goto('/challenges/official/456');
  await expect(page.getByText('2026.09.01 ~ 2026.10.07', { exact: true })).toBeVisible();
});

test('My and participation details use full dates without changing end-date policy', async ({ page }) => {
  await page.route('**/api/v1/user/challenges', route =>
    fulfillJson(route, { items: [officialParticipation], total_count: 1 }));
  await page.route('**/api/v1/user/challenges/501', route => fulfillJson(route, officialParticipation));
  await page.route('**/api/v1/user/badges', route =>
    fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/custom-challenge-participations', route =>
    fulfillJson(route, { items: [customParticipation], totalCount: 1 }));
  await page.route('**/api/v1/user/custom-challenge-participations/701', route =>
    fulfillJson(route, customParticipation));

  await page.goto('/challenges');
  await page.getByRole('button', { name: '진행 중인 챌린지 펼치기', exact: true }).click();
  const officialCard = page.getByRole('article', { name: challenge.name });
  const period = officialCard.getByText('2026.10.01 ~ 2026.10.07', { exact: true });
  const rate = officialCard.getByText('14.29% 달성', { exact: true });
  await expect(period).toBeVisible();
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    const [cardBox, periodBox, rateBox] = await Promise.all([
      officialCard.boundingBox(),
      period.boundingBox(),
      rate.boundingBox(),
    ]);
    expect(cardBox).not.toBeNull();
    expect(periodBox).not.toBeNull();
    expect(rateBox).not.toBeNull();
    expect(periodBox!.x).toBeGreaterThanOrEqual(cardBox!.x);
    expect(periodBox!.x + periodBox!.width).toBeLessThanOrEqual(rateBox!.x);
    expect(rateBox!.x + rateBox!.width).toBeLessThanOrEqual(cardBox!.x + cardBox!.width);
    const rateLines = await rate.evaluate(element => {
      const style = getComputedStyle(element);
      return element.getBoundingClientRect().height / Number.parseFloat(style.lineHeight);
    });
    expect(rateLines).toBeLessThanOrEqual(1.05);
    const screenshotDirectory = process.env.UI456_SCREENSHOT_DIR;
    if (screenshotDirectory) {
      mkdirSync(screenshotDirectory, { recursive: true });
      await officialCard.screenshot({
        path: path.join(screenshotDirectory, `task-5-official-my-card-${width}.png`),
        animations: 'disabled',
      });
    }
  }
  await expect(page.getByRole('article', { name: customParticipation.challengeName })).toBeVisible();

  await page.goto('/challenges/participations/501');
  await expect(page.getByText('내 수행 기간 · 2026.10.01 ~ 2026.10.07', { exact: true })).toBeVisible();

  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByText('2026.10.01 ~ 2026.10.07', { exact: true })).toBeVisible();
});
