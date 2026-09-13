import { expect, test, type Locator, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

const longOfficialName = '매일 가볍게 걸으며 건강한 생활 습관을 오래 이어가는 공식 챌린지';
const longCustomName = '아침과 저녁의 복약 기록을 빠뜨리지 않고 꾸준히 이어가는 맞춤 챌린지';

const officialChallenge = {
  id: 101,
  name: longOfficialName,
  phrase: '매일 걸어요',
  description: null,
  challenge_type_code: 'OFFICIAL',
  period_code: 'D7',
  duration_days: 7,
  check_type_code: 'SELF',
  frequency_code: 'DAILY',
  recruit_start_at: '2026-09-01T00:00:00+09:00',
  recruit_end_at: '2026-09-30T23:59:59+09:00',
  reward_badge: null,
  can_join: true,
  participation_id: null,
};

const participatingOfficialChallenge = {
  ...officialChallenge,
  id: 102,
  name: '참여 중인 공식 챌린지',
  can_join: false,
  participation_id: 502,
};

const officialParticipation = {
  id: 501,
  user_id: 1,
  challenge_id: officialChallenge.id,
  challenge_name: longOfficialName,
  status: 'ACTIVE',
  joined_at: '2026-09-09T00:00:00+09:00',
  started_at: '2026-09-09T00:00:00+09:00',
  end_at: '2026-09-16T00:00:00+09:00',
  target_count: 7,
  completed_count: 2,
  progress_rate: '28.57',
  completed_at: null,
  cancelled_at: null,
  progress_periods: [],
  challenge: { ...officialChallenge, can_join: false, participation_id: 501 },
  today: '2026-09-10',
  today_verification: null,
  can_verify: true,
  verified_dates: ['2026-09-09'],
};

const participatingOfficial = {
  ...officialParticipation,
  id: 502,
  challenge_id: participatingOfficialChallenge.id,
  challenge_name: participatingOfficialChallenge.name,
  challenge: participatingOfficialChallenge,
};

const customParticipation = {
  id: 701,
  templateId: 41,
  challengeType: 'MEDICATION',
  challengeName: longCustomName,
  rewardBadge: null,
  status: 'ACTIVE',
  joinedAt: '2026-09-09T00:00:00+09:00',
  endAt: '2026-09-16T00:00:00+09:00',
  actualEndDate: '2026-09-15',
  targetCount: 7,
  completedCount: 2,
  progressRate: '28.57',
  targetDayCount: 7,
  completedDayCount: 2,
  dayProgressRate: '28.57',
  action: 'NONE',
  targets: [{ id: 901, sourceId: 201, name: '아침 처방약' }],
  occurrences: [],
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function expectBadgeImmediatelyBeforeTitle(card: Locator, titleText: string, badgeText: '공식' | '맞춤') {
  const title = card.getByText(titleText, { exact: true });
  const badge = card.getByText(badgeText, { exact: true });
  await expect(title).toBeVisible();
  await expect(badge).toBeVisible();

  expect(await title.evaluate((element, expectedBadge) => (
    element.previousElementSibling?.textContent?.trim() === expectedBadge
  ), badgeText)).toBe(true);

  const [badgeBox, titleBox] = await Promise.all([badge.boundingBox(), title.boundingBox()]);
  expect(badgeBox).not.toBeNull();
  expect(titleBox).not.toBeNull();
  expect(Math.abs(badgeBox!.y - titleBox!.y)).toBeLessThanOrEqual(2);
  expect(badgeBox!.x + badgeBox!.width).toBeLessThanOrEqual(titleBox!.x + 1);
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-10T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'issue-456-badge-token');
    sessionStorage.setItem('poke.account-principal', 'issue-456-badge@example.com');
  });
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route =>
    fulfillJson(route, { code: 'FIXTURE_MISSING', message: '456 badge fixture missing' }, 503));
  await page.route('**/api/v1/user/badges', route => fulfillJson(route, { items: [], total_count: 0 }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => fulfillJson(route, { items: [], totalCount: 0 }));
});

test('320px 둘러보기에서 공식·맞춤 배지가 제목 바로 앞에 있고 참여 상태와 상세 동작을 유지한다', async ({ page }, testInfo) => {
  const recommendations = [
    {
      templateId: 41,
      challengeType: 'MEDICATION',
      challengeName: longCustomName,
      rewardBadge: null,
      action: 'NONE',
      targets: [{ id: 201, name: '아침 처방약', existingParticipationId: null }],
    },
    {
      templateId: 42,
      challengeType: 'SUPPLEMENT',
      challengeName: '참여 중인 맞춤 챌린지',
      rewardBadge: null,
      action: 'NONE',
      targets: [{ id: 202, name: '비타민', existingParticipationId: 702 }],
    },
  ];
  await page.setViewportSize({ width: 320, height: 900 });
  await page.route('**/api/v1/user/challenge-catalog?*', route => fulfillJson(route, {
    items: [officialChallenge, participatingOfficialChallenge],
    total_count: 2,
    offset: 0,
    limit: 100,
  }));
  await page.route('**/api/v1/user/challenges', route => fulfillJson(route, { items: [participatingOfficial], total_count: 1 }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => fulfillJson(route, { items: recommendations, totalCount: 2 }));

  await page.goto('/challenges/browse');
  const officialRegion = page.getByRole('region', { name: '공식 챌린지', exact: true });
  const customRegion = page.getByRole('region', { name: '맞춤 챌린지', exact: true });
  await officialRegion.getByRole('button', { name: '공식 챌린지 펼치기', exact: true }).click();
  await customRegion.getByRole('button', { name: '맞춤 챌린지 펼치기', exact: true }).click();

  const officialDetail = officialRegion.getByRole('button', { name: `${longOfficialName} 자세히 보기`, exact: true });
  const officialParticipating = officialRegion.getByRole('button', { name: '참여 중인 공식 챌린지 참여중', exact: true });
  const customDetail = customRegion.getByRole('button', { name: `${longCustomName} 대상 선택`, exact: true });
  const customParticipating = customRegion.getByRole('button', { name: '참여 중인 맞춤 챌린지 참여중', exact: true });
  await expectBadgeImmediatelyBeforeTitle(officialDetail, longOfficialName, '공식');
  await expectBadgeImmediatelyBeforeTitle(officialParticipating, participatingOfficialChallenge.name, '공식');
  await expectBadgeImmediatelyBeforeTitle(customDetail, longCustomName, '맞춤');
  await expectBadgeImmediatelyBeforeTitle(customParticipating, recommendations[1].challengeName, '맞춤');
  await expect(officialDetail).toBeEnabled();
  await expect(customDetail).toBeEnabled();
  await expect(officialParticipating).toBeDisabled();
  await expect(customParticipating).toBeDisabled();
  await officialDetail.focus();
  await expect(officialDetail).toBeFocused();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('challenge-badges-browse-320.png'), fullPage: true, animations: 'disabled' });
  await officialDetail.click();
  await expect(page).toHaveURL('/challenges/official/101');
});

for (const width of [320, 390]) {
  test(`${width}px 나의 챌린지에서 공식·맞춤 배지가 제목 바로 앞에 있고 상세 링크를 유지한다`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route('**/api/v1/user/challenges', route => fulfillJson(route, { items: [officialParticipation], total_count: 1 }));
    await page.route('**/api/v1/user/custom-challenge-participations', route => fulfillJson(route, { items: [customParticipation], totalCount: 1 }));

    await page.goto('/challenges');
    await page.getByRole('button', { name: '진행 중인 챌린지 펼치기', exact: true }).click();

    const officialCard = page.getByRole('article', { name: longOfficialName, exact: true });
    const customCard = page.getByRole('article', { name: longCustomName, exact: true });
    await expectBadgeImmediatelyBeforeTitle(officialCard, longOfficialName, '공식');
    await expectBadgeImmediatelyBeforeTitle(customCard, longCustomName, '맞춤');

    const officialDetail = officialCard.getByRole('link', { name: `${longOfficialName} 자세히 보기`, exact: true });
    const customDetail = customCard.getByRole('link', { name: `${longCustomName} 자세히 보기`, exact: true });
    await expect(officialDetail).toHaveAttribute('href', '/challenges/participations/501');
    await expect(customDetail).toHaveAttribute('href', '/challenges/custom-participations/701');
    await customDetail.focus();
    await expect(customDetail).toBeFocused();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`challenge-badges-my-${width}.png`), fullPage: true, animations: 'disabled' });
    await customDetail.click();
    await expect(page).toHaveURL('/challenges/custom-participations/701');
  });
}
