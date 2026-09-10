import { readFileSync } from 'node:fs';
import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const WATER_BADGE_PNG = readFileSync(new URL('../../../app/static/media/badges/water-badge.png', import.meta.url));

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(120_000);
test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
});

const badge = {
  id: 31,
  name: '튼튼 걷기 배지',
  description: '꾸준한 걷기를 기록했어요.',
  image_path: '/images/challenges/badge-walk.png',
};

const dailyChallenge = {
  id: 101,
  name: '매일 30분 걷기',
  phrase: '걷기로 채우는 나의 2주',
  description: '하루 한 번 걷고 직접 기록해요.',
  challenge_type_code: 'OFFICIAL',
  period_code: 'D14',
  duration_days: 14,
  check_type_code: 'SELF',
  frequency_code: 'DAILY',
  recruit_start_at: '2026-09-01T00:00:00+09:00',
  recruit_end_at: '2026-09-30T23:59:59+09:00',
  reward_badge: badge,
  can_join: true,
  participation_id: null,
};

const manualChallenge = {
  ...dailyChallenge,
  id: 102,
  name: '건강 기록 제출하기',
  phrase: '기간 안에 열 번 기록해요',
  description: null,
  period_code: 'D30',
  duration_days: 30,
  check_type_code: 'MANUAL',
  frequency_code: 'TOTAL_10',
  reward_badge: null,
  can_join: true,
};

const weeklyChallenge = {
  ...dailyChallenge,
  id: 103,
  name: '가볍게 스트레칭',
  phrase: '일주일에 세 번 몸을 깨워요',
  period_code: 'D14',
  duration_days: 14,
  frequency_code: 'WEEKLY_3',
  reward_badge: null,
};

function participation(overrides: Record<string, unknown> = {}) {
  return {
    id: 501,
    user_id: 7,
    challenge_id: 101,
    challenge_name: dailyChallenge.name,
    status: 'ACTIVE',
    joined_at: '2026-09-08T10:00:00+09:00',
    started_at: '2026-09-08T00:00:00+09:00',
    end_at: '2026-09-22T00:00:00+09:00',
    target_count: 14,
    completed_count: 3,
    progress_rate: '21.43',
    completed_at: null,
    cancelled_at: null,
    progress_periods: [{
      id: 801,
      period_start: '2026-09-08',
      period_end: '2026-09-21',
      target_count: 14,
      completed_count: 3,
      progress_rate: '21.43',
      is_completed: false,
      completed_at: null,
    }],
    challenge: { ...dailyChallenge, can_join: false, participation_id: 501 },
    today: '2026-09-10',
    today_verification: null,
    can_verify: true,
    verified_dates: ['2026-09-08', '2026-09-09'],
    ...overrides,
  };
}

function cancelledAttempt(canJoin = true, latestId = 501) {
  return participation({
    status: 'CANCELLED', cancelled_at: '2026-09-10T12:00:00+09:00', can_verify: false,
    challenge: { ...dailyChallenge, can_join: canJoin, participation_id: latestId },
  });
}

test('My combines official and custom active cards and all past statuses without id collisions', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'mixed-challenges-test');
    sessionStorage.setItem('poke.account-principal', 'mixed-challenges@example.com');
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: {
    items: [participation(), participation({ id: 502, challenge_name: '지난 공식 걷기', status: 'EXPIRED', can_verify: false })], total_count: 2,
  } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  const custom = {
    id: 501, templateId: 31, challengeType: 'MEDICATION', challengeName: '처방 일정 지키기',
    rewardBadge: null, status: 'ACTIVE', joinedAt: '2026-09-09T09:00:00+09:00', endAt: '2026-09-16T09:00:00+09:00',
    actualEndDate: '2026-09-16', targetCount: 14, completedCount: 5, progressRate: '35.71', action: 'NONE',
    targets: [{ id: 801, sourceId: 101, name: '서울의원 처방' }], occurrences: [],
  };
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: {
    items: [custom,
      { ...custom, id: 502, status: 'COMPLETED', challengeName: '달성한 복약', progressRate: '100.00', completedCount: 14 },
      { ...custom, id: 503, status: 'EXPIRED', challengeType: 'SUPPLEMENT', challengeName: '종료한 영양제' },
      { ...custom, id: 504, status: 'CANCELLED', challengeName: '취소한 복약' }], totalCount: 4,
  } }));
  await page.goto('/challenges');
  const active = page.getByRole('region', { name: '진행 중인 챌린지', exact: true });
  await expect(active.getByRole('article')).toHaveCount(2);
  await expect(active.getByRole('link', { name: '매일 30분 걷기 자세히 보기' })).toHaveAttribute('href', '/challenges/participations/501');
  await expect(active.getByRole('link', { name: '처방 일정 지키기 자세히 보기' })).toHaveAttribute('href', '/challenges/custom-participations/501');
  await expect(active.getByText('공식', { exact: true })).toBeVisible();
  await expect(active.getByText('맞춤', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '지난 기록 펼치기' })).toHaveText('4개 보기');
  await page.getByRole('button', { name: '지난 기록 펼치기' }).click();
  const history = page.getByRole('region', { name: '지난 기록', exact: true });
  await expect(history.getByRole('article')).toHaveCount(4);
  await expect(history.getByRole('link', { name: '달성한 복약 자세히 보기' })).toHaveAttribute('href', '/challenges/custom-participations/502');
  await expect(history.getByRole('article', { name: '종료한 영양제' })).toContainText('종료');
  await expect(history.getByRole('article', { name: '취소한 복약' })).toContainText('취소');
  await expect(history.getByRole('link', { name: '지난 공식 걷기 자세히 보기' })).toHaveAttribute('href', '/challenges/participations/502');
  await history.screenshot({ path: testInfo.outputPath('combined-history.png') });
  await page.getByRole('button', { name: '지난 기록 접기' }).click();
  await expect(history.getByRole('article')).toHaveCount(0);
  await expect(active.getByRole('article')).toHaveCount(2);
});

function restartedAttempt() {
  return participation({
    id: 502, completed_count: 0, progress_rate: '0.00', verified_dates: [],
    joined_at: '2026-09-10T13:00:00+09:00', started_at: '2026-09-10T00:00:00+09:00',
    end_at: '2026-09-24T00:00:00+09:00',
    progress_periods: [{ id: 802, period_start: '2026-09-10', period_end: '2026-09-23',
      target_count: 14, completed_count: 0, progress_rate: '0.00', is_completed: false, completed_at: null }],
    challenge: { ...dailyChallenge, can_join: false, participation_id: 502 },
  });
}

for (const entry of ['participation', 'catalog'] as const) {
  test(`rejoin from ${entry} confirms reset and shows a new attempt with zero progress`, async ({ page }) => {
    test.setTimeout(30_000);
    await authenticate(page);
    await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: { code: 'NOT_FOUND', message: '없음' } }));
    await stubChallengeReads(page, { catalog: [cancelledAttempt().challenge] });
    let joined = false;
    let joinCalls = 0;
    await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: {
      items: joined ? [restartedAttempt(), cancelledAttempt(false, 502)] : [cancelledAttempt()],
      total_count: joined ? 2 : 1,
    } }));
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v1/user/challenge-catalog/101', route => route.fulfill({ json: cancelledAttempt().challenge }));
    await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: cancelledAttempt(!joined, joined ? 502 : 501) }));
    await page.route('**/api/v1/user/challenges/502', route => route.fulfill({ json: restartedAttempt() }));
    await page.route('**/api/v1/user/challenges/101/join', async route => {
      joinCalls += 1;
      expect(route.request().postData()).toBeNull();
      await gate;
      joined = true;
      await route.fulfill({ status: 201, json: restartedAttempt() });
    });
    await page.goto(entry === 'participation' ? '/challenges/participations/501' : '/challenges/browse');
    if (entry === 'catalog') {
      await page.getByRole('button', { name: /매일 30분 걷기.*자세히 보기/ }).click();
      await expect(page).toHaveURL(/\/challenges\/official\/101$/);
    }
    await page.getByRole('button', { name: '다시 참여하기', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('0%');
    await expect(dialog).toContainText('수행 기간');
    expect(joinCalls).toBe(0);
    await dialog.getByRole('button', { name: '다시 참여하기', exact: true }).click();
    const submitting = dialog.getByRole('button', { name: '참여 중', exact: true });
    await expect(submitting).toBeDisabled();
    await submitting.evaluate((element: HTMLButtonElement) => element.click());
    expect(joinCalls).toBe(1);
    release();
    await expect(page).toHaveURL(/\/challenges\/participations\/502$/);
    await expect(page.getByRole('progressbar', { name: '내 인증 기록 진행률' })).toHaveAttribute('aria-valuenow', '0');
    await expect(page.getByText('내 수행 기간 · 2026.9.10 ~ 2026.9.23')).toBeVisible();
    await expect(page.getByLabel('2026-09-10 미인증', { exact: true })).toBeVisible();
    await page.goto('/challenges/participations/501');
    await expect(page.getByRole('progressbar', { name: '내 인증 기록 진행률' })).toHaveAttribute('aria-valuenow', '21.43');
    await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: '진행 보기', exact: true }).click();
    await expect(page).toHaveURL(/\/challenges\/participations\/502$/);
    expect(joinCalls).toBe(1);
    await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
    const active = page.getByRole('region', { name: '진행 중인 챌린지', exact: true });
    await expect(active.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    await expect(active.getByRole('link', { name: /매일 30분 걷기 자세히 보기/ })).toHaveAttribute('href', '/challenges/participations/502');
    await page.getByRole('button', { name: '지난 기록 펼치기' }).click();
    const history = page.getByRole('region', { name: '지난 기록', exact: true });
    await expect(history.getByRole('link', { name: /매일 30분 걷기 자세히 보기/ })).toHaveAttribute('href', '/challenges/participations/501');
    await page.getByRole('button', { name: '홈', exact: true }).click();
    await expect(page.getByRole('link', { name: '매일 30분 걷기, 0% 진행 중, 상세 보기', exact: true })).toHaveAttribute('href', '/challenges/participations/502');
  });
}

test('rejoin from an older history starts another attempt when the latest attempt was also cancelled', async ({ page }) => {
  test.setTimeout(20_000);
  await authenticate(page);
  await stubChallengeReads(page);
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: cancelledAttempt(true, 502) }));
  const thirdAttempt = { ...restartedAttempt(), id: 503, challenge: { ...restartedAttempt().challenge, participation_id: 503 } };
  await page.route('**/api/v1/user/challenges/503', route => route.fulfill({ json: thirdAttempt }));
  await page.route('**/api/v1/user/challenges/101/join', route => route.fulfill({ status: 201, json: thirdAttempt }));
  await page.goto('/challenges/participations/501');
  await page.getByRole('button', { name: '다시 참여하기', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '다시 참여하기', exact: true }).click();
  await expect(page).toHaveURL(/\/challenges\/participations\/503$/);
  await expect(page.getByRole('progressbar', { name: '내 인증 기록 진행률' })).toHaveAttribute('aria-valuenow', '0');
});

for (const deadline of ['2026-09-09T00:00:00+09:00', '2026-09-10T12:00:00+09:00']) {
  test(`rejoin is unavailable for a cancelled attempt after recruitment closes at ${deadline}`, async ({ page }) => {
    test.setTimeout(20_000);
    await page.clock.setFixedTime(new Date('2026-09-10T13:00:00+09:00'));
    await authenticate(page);
    await stubChallengeReads(page);
    await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: {
      ...cancelledAttempt(false), challenge: { ...cancelledAttempt(false).challenge, recruit_end_at: deadline },
    } }));
    await page.goto('/challenges/participations/501');
    await expect(page.getByText('모집이 마감됐어요', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toHaveCount(0);
  });
}

for (const outcome of ['closed', 'already-joined', 'response-lost'] as const) {
  test(`rejoin reconciles ${outcome} after the cancelled page was opened`, async ({ page }) => {
    test.setTimeout(20_000);
    await authenticate(page);
    await stubChallengeReads(page);
    let submitted = false;
    await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: cancelledAttempt(!submitted, submitted && outcome !== 'closed' ? 502 : 501) }));
    await page.route('**/api/v1/user/challenges/502', route => route.fulfill({ json: restartedAttempt() }));
    await page.route('**/api/v1/user/challenges/101/join', route => {
      submitted = true;
      return route.fulfill({ status: outcome === 'response-lost' ? 503 : 409, json: {
        code: outcome === 'closed' ? 'CHALLENGE_RECRUITMENT_CLOSED' : 'CHALLENGE_ALREADY_JOINED',
        message: outcome === 'closed' ? '모집이 마감됐어요' : '이미 참여 중이에요',
      } });
    });
    await page.goto('/challenges/participations/501');
    await page.getByRole('button', { name: '다시 참여하기', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: '다시 참여하기', exact: true }).click();
    if (outcome === 'closed') {
      await expect(page.getByRole('alert')).toContainText('모집이 마감');
      await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toHaveCount(0);
      await expect(page).toHaveURL(/\/challenges\/participations\/501$/);
    } else {
      await expect(page).toHaveURL(/\/challenges\/participations\/502$/);
    }
  });
}

for (const outcome of ['leave', 'unauthorized'] as const) {
  test(`rejoin ignores stale completion on ${outcome}`, async ({ page }) => {
    test.setTimeout(20_000);
    await authenticate(page);
    await stubChallengeReads(page);
    let reads = 0;
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v1/user/challenges/501', route => {
      reads += 1;
      return route.fulfill({ json: cancelledAttempt() });
    });
    await page.route('**/api/v1/user/challenges/101/join', async route => {
      await gate;
      await route.fulfill(outcome === 'leave' ? { status: 201, json: restartedAttempt() } :
        { status: 401, json: { code: 'UNAUTHORIZED', message: '로그인이 필요해요' } });
    });
    await page.goto('/challenges/participations/501');
    await page.getByRole('button', { name: '다시 참여하기', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: '다시 참여하기', exact: true }).click();
    await expect(page.getByRole('button', { name: '참여 중', exact: true })).toBeDisabled();
    const readsBefore = reads;
    if (outcome === 'leave') {
      await page.evaluate(() => {
        window.history.pushState({}, '', '/challenges/browse');
        window.dispatchEvent(new PopStateEvent('popstate'));
      });
      await expect(page.getByRole('combobox', { name: '챌린지 종류 필터' })).toBeVisible();
    }
    release();
    if (outcome === 'unauthorized') await expect(page).toHaveURL(/\/login$/);
    else await page.waitForTimeout(100);
    await expect(page).not.toHaveURL(/\/challenges\/participations\/502$/);
    expect(reads).toBe(readsBefore);
  });
}

async function authenticate(page: Page, principal = 'challenge-api@example.com') {
  await page.addInitScript(({ principal }) => {
    sessionStorage.setItem('poke.access-token', `token-for-${principal}`);
    sessionStorage.setItem('poke.account-principal', principal);
  }, { principal });
}

async function stubChallengeReads(
  page: Page,
  options: {
    catalog?: unknown[];
    participations?: unknown[];
    badges?: unknown[];
    customBadges?: unknown[];
  } = {},
) {
  const catalog = options.catalog ?? [manualChallenge, weeklyChallenge, dailyChallenge];
  const participations = options.participations ?? [];
  const badges = options.badges ?? [];
  const customBadges = options.customBadges ?? [];
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: catalog, total_count: catalog.length, offset: 0, limit: 100 },
  }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({
    json: { items: participations, total_count: participations.length },
  }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({
    json: { items: badges, total_count: badges.length },
  }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({
    json: { items: customBadges, totalCount: customBadges.length },
  }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
}

test('real My and browse keep the shared back navigation', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  await page.goto('/challenges');
  await page.getByRole('link', { name: '둘러보기', exact: true }).click();
  const back = page.getByRole('button', { name: '뒤로 가기', exact: true });
  await expect(back).toBeVisible();
  await back.click();
  await expect(page).toHaveURL(/\/challenges$/);
  await back.click();
  await expect(page).toHaveURL(/\/home$/);
});

test('real browse renders compact recruitment dates from the catalog and never shows mock data', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);

  await page.goto('/challenges/browse');

  await expect(page.getByRole('combobox', { name: '챌린지 종류 필터' })).toHaveValue('all');
  for (const name of ['매일 30분 걷기', '건강 기록 제출하기', '가볍게 스트레칭']) {
    await expect(page.getByRole('button', { name: `${name} 자세히 보기` })).toContainText('모집기간 : 2026년 9월 1일 ~ 2026년 9월 30일');
  }
  await expect(page.getByText('목업 미리보기')).toHaveCount(0);
  await expect(page.getByText('물 마시기', { exact: true })).toHaveCount(0);
});

test('SELF detail joins once with no body and routes to the returned participation', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  await page.route('**/api/v1/user/challenge-catalog/101', route => route.fulfill({ json: dailyChallenge }));
  let joinCalls = 0;
  let joinBody: string | null = 'not-called';
  let finishJoin!: () => void;
  const joinGate = new Promise<void>(resolve => {
    finishJoin = resolve;
  });
  await page.route('**/api/v1/user/challenges/101/join', async route => {
    joinCalls += 1;
    joinBody = route.request().postData();
    await joinGate;
    await route.fulfill({ status: 201, json: participation() });
  });
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation() }));

  await page.goto('/challenges/official/101');

  await expect(page.getByRole('heading', { name: dailyChallenge.name })).toBeVisible();
  await expect(page.getByText('참여 당일부터 14일', { exact: true })).toBeVisible();
  await expect(page.getByText('하루 한 번 걷고 직접 기록해요.')).toBeVisible();
  const join = page.getByRole('button', { name: '참여하기', exact: true });
  await join.click();
  const joining = page.getByRole('button', { name: '참여 중', exact: true });
  await expect(joining).toBeDisabled();
  await joining.evaluate((element: HTMLButtonElement) => element.click());
  expect(joinCalls).toBe(1);
  finishJoin();
  await expect(page).toHaveURL(/\/challenges\/participations\/501$/);
  expect(joinCalls).toBe(1);
  expect(joinBody).toBeNull();
});

test('a lost join response reconciles the committed participation from catalog detail', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  let joined = false;
  let detailReads = 0;
  let joinCalls = 0;
  await page.route('**/api/v1/user/challenge-catalog/101', route => {
    detailReads += 1;
    return route.fulfill({ json: {
      ...dailyChallenge,
      can_join: !joined,
      participation_id: joined ? 501 : null,
    } });
  });
  await page.route('**/api/v1/user/challenges/101/join', route => {
    joinCalls += 1;
    joined = true;
    return route.fulfill({
      status: 503,
      json: { code: 'RESPONSE_LOST', message: '참여 응답을 받지 못했어요.' },
    });
  });
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation() }));

  await page.goto('/challenges/official/101');
  await page.getByRole('button', { name: '참여하기' }).click();

  await expect(page).toHaveURL(/\/challenges\/participations\/501$/);
  await expect(page.getByRole('heading', { name: dailyChallenge.name })).toBeVisible();
  expect(joinCalls).toBe(1);
  expect(detailReads).toBeGreaterThanOrEqual(2);
});

for (const status of [401, 403] as const) {
  test(`join ${status} does not reconcile a definitive authorization failure`, async ({ page }) => {
    await authenticate(page);
    await stubChallengeReads(page);
    let detailReads = 0;
    await page.route('**/api/v1/user/challenge-catalog/101', route => {
      detailReads += 1;
      return route.fulfill({ json: dailyChallenge });
    });
    await page.route('**/api/v1/user/challenges/101/join', route => route.fulfill({
      status,
      json: { code: status === 401 ? 'UNAUTHORIZED' : 'FORBIDDEN', message: '참여 권한이 없어요.' },
    }));

    await page.goto('/challenges/official/101');
    await expect(page.getByRole('heading', { name: dailyChallenge.name })).toBeVisible();
    const readsBeforeJoin = detailReads;
    await page.getByRole('button', { name: '참여하기' }).click();
    await page.waitForTimeout(100);

    expect(detailReads).toBe(readsBeforeJoin);
    await expect(page).not.toHaveURL(/\/challenges\/participations\//);
  });
}

test('a delayed join cannot navigate after the same account moves to another challenge detail', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  let finishJoin!: () => void;
  const joinGate = new Promise<void>(resolve => {
    finishJoin = resolve;
  });
  await page.route('**/api/v1/user/challenge-catalog/101', route => route.fulfill({ json: dailyChallenge }));
  await page.route('**/api/v1/user/challenge-catalog/103', route => route.fulfill({ json: weeklyChallenge }));
  await page.route('**/api/v1/user/challenges/101/join', async route => {
    await joinGate;
    await route.fulfill({ status: 201, json: participation() });
  });

  await page.goto('/challenges/official/101');
  await page.getByRole('button', { name: '참여하기' }).click();
  await page.evaluate(() => {
    window.history.pushState({}, '', '/challenges/official/103');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page.getByRole('heading', { name: weeklyChallenge.name })).toBeVisible();
  finishJoin();

  await page.waitForTimeout(100);
  await expect(page).toHaveURL(/\/challenges\/official\/103$/);
  await expect(page.getByRole('heading', { name: weeklyChallenge.name })).toBeVisible();
});

test('MANUAL detail explains unsupported verification and never joins', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  let joinCalls = 0;
  await page.route('**/api/v1/user/challenge-catalog/102', route => route.fulfill({ json: manualChallenge }));
  await page.route('**/api/v1/user/challenges/102/join', route => {
    joinCalls += 1;
    return route.fulfill({ status: 500 });
  });

  await page.goto('/challenges/official/102');

  await expect(page.getByText('관리자 확인 방식은 현재 앱에서 참여할 수 없어요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '현재 앱에서는 참여할 수 없어요' })).toBeDisabled();
  expect(joinCalls).toBe(0);
});

test('invalid challenge ids render not-found without issuing a detail or join request', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  const challengeRequests: string[] = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path.includes('/challenge-catalog/') || path.endsWith('/join')) challengeRequests.push(path);
  });

  await page.goto('/challenges/official/not-a-number');

  await expect(page.getByRole('heading', { name: '챌린지를 찾을 수 없어요' })).toBeVisible();
  expect(challengeRequests).toEqual([]);
});

test('my card trusts server progress and retries SELF check-in with the same idempotency key', async ({ page }) => {
  await authenticate(page);
  const before = participation();
  const after = participation({
    completed_count: 4,
    progress_rate: '28.57',
    can_verify: false,
    today_verification: {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    },
    verified_dates: ['2026-09-08', '2026-09-09', '2026-09-10'],
  });
  let refreshed = false;
  let listReads = 0;
  let badgeReads = 0;
  const verificationBodies: Array<{ verification_date: string; idempotency_key: string }> = [];
  let finishFirstVerification!: () => void;
  const firstVerificationGate = new Promise<void>(resolve => {
    finishFirstVerification = resolve;
  });
  await page.route('**/api/v1/user/challenges', route => {
    listReads += 1;
    const items = [refreshed ? after : before];
    return route.fulfill({ json: { items, total_count: items.length } });
  });
  await page.route('**/api/v1/user/badges', route => {
    badgeReads += 1;
    return route.fulfill({ json: { items: [], total_count: 0 } });
  });
  await page.route('**/api/v1/user/challenges/501/verifications', async route => {
    verificationBodies.push(route.request().postDataJSON());
    if (verificationBodies.length === 1) {
      await firstVerificationGate;
      await route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '잠시 연결이 끊겼어요.' } });
      return;
    }
    refreshed = true;
    await route.fulfill({ status: 201, json: after.today_verification });
  });

  await page.goto('/challenges');

  const card = page.getByRole('article', { name: dailyChallenge.name });
  await expect(card.getByText('3 / 14일 인증')).toBeVisible();
  await expect(card.getByText('21.43% 달성')).toBeVisible();
  await card.getByRole('button', { name: '했어요' }).click();
  const checking = card.getByRole('button', { name: '인증 기록 중' });
  await expect(checking).toBeDisabled();
  await checking.evaluate((element: HTMLButtonElement) => element.click());
  expect(verificationBodies).toHaveLength(1);
  finishFirstVerification();
  await expect(card.getByRole('alert')).toContainText('잠시 연결이 끊겼어요.');
  await card.getByRole('button', { name: '했어요' }).click();
  await expect(card.getByText('4 / 14일 인증')).toBeVisible();
  await expect(card.getByRole('button', { name: '오늘 인증 완료' })).toBeDisabled();

  expect(verificationBodies).toHaveLength(2);
  expect(verificationBodies[0].verification_date).toBe('2026-09-10');
  expect(verificationBodies[0].idempotency_key).toMatch(/^[0-9a-f-]{16,64}$/i);
  expect(verificationBodies[1].idempotency_key).toBe(verificationBodies[0].idempotency_key);
  expect(listReads).toBeGreaterThan(1);
  expect(badgeReads).toBeGreaterThan(1);
});

test('My keeps a successful check-in when optional catalog and badge refreshes fail', async ({ page }) => {
  await authenticate(page);
  const before = participation();
  const after = participation({
    completed_count: 4,
    progress_rate: '28.57',
    can_verify: false,
    today_verification: {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    },
    verified_dates: ['2026-09-08', '2026-09-09', '2026-09-10'],
  });
  let checked = false;
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    status: 503,
    json: { code: 'TEMPORARY', message: '카탈로그를 불러오지 못했어요.' },
  }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: {
    items: [checked ? after : before], total_count: 1,
  } }));
  await page.route('**/api/v1/user/badges', route => {
    return checked
      ? route.fulfill({
        status: 503,
        json: { code: 'TEMPORARY', message: '배지 정보를 불러오지 못했어요.' },
      })
      : route.fulfill({ json: { items: [], total_count: 0 } });
  });
  await page.route('**/api/v1/user/challenges/501/verifications', route => {
    checked = true;
    return route.fulfill({ status: 201, json: after.today_verification });
  });

  await page.goto('/challenges');
  const card = page.getByRole('article', { name: dailyChallenge.name });
  await card.getByRole('button', { name: '했어요' }).click();

  await expect(card.getByText('4 / 14일 인증')).toBeVisible();
  await expect(card.getByRole('button', { name: '오늘 인증 완료' })).toBeDisabled();
  await expect(card.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('alert')).toContainText('배지 정보를 불러오지 못했어요.');
});

test('participation rotates the existing badge once only after GET confirms a new award', async ({ page }, testInfo) => {
  await authenticate(page);
  const waterBadge = {
    ...badge,
    name: '물마시기 배지',
    image_path: 'media/badges/water-badge.png',
  };
  const waterChallenge = { ...dailyChallenge, can_join: false, participation_id: 501, reward_badge: waterBadge };
  const verification = {
    id: 901,
    user_challenge_id: 501,
    progress_id: 801,
    verification_date: '2026-09-10',
    content: null,
    image_path: null,
    status: 'APPROVED',
    rejection_reason: null,
    reviewed_by_admin_id: null,
    reviewed_at: '2026-09-10T11:00:00+09:00',
    submitted_at: '2026-09-10T11:00:00+09:00',
  };
  const before = participation({ completed_count: 13, progress_rate: '92.86', challenge: waterChallenge });
  const after = participation({
    status: 'COMPLETED',
    completed_count: 14,
    progress_rate: '100.00',
    completed_at: '2026-09-10T11:00:00+09:00',
    can_verify: false,
    today_verification: verification,
    verified_dates: ['2026-09-10'],
    challenge: waterChallenge,
  });
  const awardedBadge = {
    id: 702,
    user_id: 7,
    badge_id: waterBadge.id,
    challenge_id: dailyChallenge.id,
    user_challenge_id: 501,
    status: 'AWARDED',
    badge_name: waterBadge.name,
    badge_image_path: waterBadge.image_path,
    awarded_at: '2026-09-10T11:00:00+09:00',
    revoked_at: null,
    revoke_reason: null,
  };
  let checked = false;
  let badgeReads = 0;
  let releaseBadgeImage!: () => void;
  const badgeImageGate = new Promise<void>(resolve => {
    releaseBadgeImage = resolve;
  });
  await page.route('**/api/v1/user/challenges/501', route =>
    route.fulfill({ json: checked ? after : before }),
  );
  await page.route('**/api/v1/user/badges', route => {
    badgeReads += 1;
    const items = checked ? [awardedBadge] : [];
    return route.fulfill({ json: { items, total_count: items.length } });
  });
  await page.route('**/api/v1/user/challenges/501/verifications', route => {
    checked = true;
    return route.fulfill({ status: 201, json: verification });
  });
  await page.route('**/media/badges/water-badge.png', async route => {
    await badgeImageGate;
    await route.fulfill({ status: 200, contentType: 'image/png', body: WATER_BADGE_PNG });
  });

  await page.goto('/challenges/participations/501');
  await page.getByRole('button', { name: '했어요', exact: true }).click();

  const completion = page.getByRole('region', { name: '챌린지 완료 결과' });
  const awardedArt = completion.getByRole('img', { name: waterBadge.name });
  await expect(awardedArt).toHaveAttribute('data-newly-awarded', 'true');
  await expect(awardedArt).toHaveCSS('animation-name', 'none');
  expect(await awardedArt.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(false);
  releaseBadgeImage();
  await expect.poll(() => awardedArt.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(true);
  await expect(awardedArt).toHaveAttribute('data-award-art-ready', 'true');
  await expect(awardedArt).toHaveCSS('animation-name', 'rx-badge-award-turn');
  await expect(awardedArt).toHaveCSS('animation-iteration-count', '1');
  await awardedArt.evaluate(element => {
    const animation = element.getAnimations().find(item => item.animationName === 'rx-badge-award-turn');
    animation?.pause();
    if (animation) animation.currentTime = 380;
  });
  await page.screenshot({ path: testInfo.outputPath('water-contour-rotation-390x844.png') });
  expect(badgeReads).toBeGreaterThanOrEqual(2);

  await page.reload();
  const revisitedArt = page.getByRole('region', { name: '챌린지 완료 결과' })
    .getByRole('img', { name: waterBadge.name });
  await expect(revisitedArt).not.toHaveAttribute('data-newly-awarded', 'true');
  await expect(revisitedArt).toHaveCSS('animation-name', 'none');

  checked = false;
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.reload();
  await page.getByRole('button', { name: '했어요', exact: true }).click();
  const reducedArt = page.getByRole('region', { name: '챌린지 완료 결과' })
    .getByRole('img', { name: waterBadge.name });
  await expect(reducedArt).toHaveAttribute('data-newly-awarded', 'true');
  await expect(reducedArt).toHaveCSS('animation-name', 'none');
});

test('water reward clips to its own teal contour without changing other badge artwork', async ({ page }, testInfo) => {
  await authenticate(page);
  const waterBadge = {
    ...badge,
    name: '물마시기 배지',
    image_path: 'media/badges/water-badge.png',
  };
  let rewardBadge = waterBadge;
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation({
    status: 'COMPLETED',
    completed_count: 14,
    progress_rate: '100.00',
    completed_at: '2026-09-10T11:00:00+09:00',
    can_verify: false,
    challenge: { ...dailyChallenge, can_join: false, participation_id: 501, reward_badge: rewardBadge },
  }) }));
  await page.route('**/api/v1/user/badges', route => {
    const item = {
      id: 800 + rewardBadge.id,
      user_id: 7,
      badge_id: rewardBadge.id,
      challenge_id: dailyChallenge.id,
      user_challenge_id: 501,
      status: 'AWARDED',
      badge_name: rewardBadge.name,
      badge_image_path: rewardBadge.image_path,
      awarded_at: '2026-09-10T11:00:00+09:00',
      revoked_at: null,
      revoke_reason: null,
    };
    return route.fulfill({ json: { items: [item], total_count: 1 } });
  });

  await page.goto('/challenges/participations/501');
  const waterArt = page.getByRole('region', { name: '챌린지 완료 결과' })
    .getByRole('img', { name: waterBadge.name });
  await expect(waterArt).toHaveAttribute('src', '/media/badges/water-badge.png');
  await expect(waterArt).toHaveAttribute('data-award-contour', 'water');
  await expect(waterArt).toHaveCSS('clip-path', /polygon/);
  await expect(waterArt).toHaveCSS('border-radius', '0px');
  await page.screenshot({ path: testInfo.outputPath('water-contour-light-390x844.png') });
  await page.addStyleTag({ content: '[aria-label="챌린지 완료 결과"] { background: #002c68 !important; }' });
  await page.screenshot({ path: testInfo.outputPath('water-contour-dark-390x844.png') });

  rewardBadge = badge;
  await page.reload();
  const walkArt = page.getByRole('region', { name: '챌린지 완료 결과' })
    .getByRole('img', { name: badge.name });
  await expect(walkArt).not.toHaveAttribute('data-award-contour', 'water');
  await expect(walkArt).toHaveCSS('clip-path', 'none');
  await expect(walkArt).toHaveClass(/rounded-pill/);
});

test('My offers a GET-only retry when progress refresh fails after an approved check-in', async ({ page }) => {
  await authenticate(page);
  const before = participation();
  const after = participation({
    completed_count: 4,
    progress_rate: '28.57',
    can_verify: false,
    today_verification: {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    },
    verified_dates: ['2026-09-08', '2026-09-09', '2026-09-10'],
  });
  let checked = false;
  let refreshReads = 0;
  let verificationPosts = 0;
  await page.route('**/api/v1/user/challenges', route => {
    if (!checked) return route.fulfill({ json: { items: [before], total_count: 1 } });
    refreshReads += 1;
    return refreshReads === 1
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '진행 정보를 불러오지 못했어요.' } })
      : route.fulfill({ json: { items: [after], total_count: 1 } });
  });
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/challenges/501/verifications', route => {
    verificationPosts += 1;
    checked = true;
    return route.fulfill({ status: 201, json: after.today_verification });
  });

  await page.goto('/challenges');
  const card = page.getByRole('article', { name: dailyChallenge.name });
  await card.getByRole('button', { name: '했어요' }).click();

  await expect(card.getByRole('button', { name: '오늘 인증 완료' })).toBeDisabled();
  await expect(card.getByText('최신 진행 정보 확인 필요')).toBeVisible();
  await expect(card.getByText('3 / 14일 인증')).toHaveCount(0);
  await card.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(card.getByText('4 / 14일 인증')).toBeVisible();
  await expect(card.getByText('최신 진행 정보 확인 필요')).toHaveCount(0);
  expect(verificationPosts).toBe(1);
});

test('a final check-in keeps badge totals uncertain until GET-only recovery is complete', async ({ page }) => {
  await authenticate(page);
  const verification = {
    id: 901,
    user_challenge_id: 501,
    progress_id: 801,
    verification_date: '2026-09-10',
    content: null,
    image_path: null,
    status: 'APPROVED',
    rejection_reason: null,
    reviewed_by_admin_id: null,
    reviewed_at: '2026-09-10T11:00:00+09:00',
    submitted_at: '2026-09-10T11:00:00+09:00',
  };
  const before = participation({ completed_count: 13, progress_rate: '92.86' });
  const after = participation({
    status: 'COMPLETED',
    completed_count: 14,
    progress_rate: '100.00',
    completed_at: '2026-09-10T11:00:00+09:00',
    can_verify: false,
    today_verification: verification,
    verified_dates: ['2026-09-10'],
  });
  const existingBadge = {
    id: 701,
    user_id: 7,
    badge_id: 99,
    challenge_id: 109,
    user_challenge_id: 599,
    status: 'AWARDED',
    badge_name: '기존 획득 배지',
    badge_image_path: '/images/challenges/badge-review.png',
    awarded_at: '2026-09-07T12:00:00+09:00',
    revoked_at: null,
    revoke_reason: null,
  };
  const finalBadge = {
    ...existingBadge,
    id: 702,
    badge_id: badge.id,
    challenge_id: dailyChallenge.id,
    user_challenge_id: 501,
    badge_name: badge.name,
    badge_image_path: badge.image_path,
    awarded_at: '2026-09-10T11:00:00+09:00',
  };
  let checked = false;
  let challengeRefreshReads = 0;
  let badgeRefreshReads = 0;
  let verificationPosts = 0;
  await page.route('**/api/v1/user/challenges', route => {
    if (!checked) return route.fulfill({ json: { items: [before], total_count: 1 } });
    challengeRefreshReads += 1;
    return challengeRefreshReads === 1
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '진행 정보를 불러오지 못했어요.' } })
      : route.fulfill({ json: { items: [after], total_count: 1 } });
  });
  await page.route('**/api/v1/user/badges', route => {
    if (!checked) return route.fulfill({ json: { items: [existingBadge], total_count: 1 } });
    badgeRefreshReads += 1;
    return badgeRefreshReads === 2
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '배지 정보를 불러오지 못했어요.' } })
      : route.fulfill({ json: { items: [existingBadge, finalBadge], total_count: 2 } });
  });
  await page.route('**/api/v1/user/challenges/501/verifications', route => {
    verificationPosts += 1;
    checked = true;
    return route.fulfill({ status: 201, json: verification });
  });

  await page.goto('/challenges');
  const badgeSummary = page.getByRole('heading', { name: '작은 실천이 쌓이고 있어요' }).locator('..');
  const card = page.getByRole('article', { name: dailyChallenge.name });
  await expect(badgeSummary.getByText('모은 배지 1종 · 1회 획득')).toBeVisible();
  await card.getByRole('button', { name: '했어요' }).click();

  await expect(badgeSummary.getByText('최신 배지 정보 확인 필요')).toBeVisible();
  await expect(badgeSummary.getByText('모은 배지 1종 · 1회 획득')).toHaveCount(0);
  await expect(badgeSummary.getByRole('img', { name: existingBadge.badge_name })).toHaveCount(0);
  await card.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(badgeSummary.getByRole('alert')).toContainText('배지 정보를 불러오지 못했어요.');
  await badgeSummary.getByRole('button', { name: '배지 다시 불러오기' }).click();

  await expect(badgeSummary.getByText('모은 배지 2종 · 2회 획득')).toBeVisible();
  await expect(badgeSummary.getByRole('img', { name: badge.name })).toBeVisible();
  expect(verificationPosts).toBe(1);
});

test('My keeps every card refresh-required after separate approved check-ins lose their refreshes', async ({ page }) => {
  await authenticate(page);
  const first = participation();
  const second = participation({
    id: 502,
    challenge_id: weeklyChallenge.id,
    challenge_name: weeklyChallenge.name,
    challenge: { ...weeklyChallenge, can_join: false, participation_id: 502 },
  });
  let verificationPosts = 0;
  await page.route('**/api/v1/user/challenges', route => {
    if (verificationPosts === 0) {
      return route.fulfill({ json: { items: [first, second], total_count: 2 } });
    }
    return route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '진행 정보를 불러오지 못했어요.' } });
  });
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/challenges/*/verifications', route => {
    verificationPosts += 1;
    const participationId = Number(new URL(route.request().url()).pathname.split('/').at(-2));
    return route.fulfill({
      status: 201,
      json: {
        id: 900 + participationId,
        user_challenge_id: participationId,
        progress_id: 800 + participationId,
        verification_date: '2026-09-10',
        content: null,
        image_path: null,
        status: 'APPROVED',
        rejection_reason: null,
        reviewed_by_admin_id: null,
        reviewed_at: '2026-09-10T11:00:00+09:00',
        submitted_at: '2026-09-10T11:00:00+09:00',
      },
    });
  });

  await page.goto('/challenges');
  const firstCard = page.getByRole('article', { name: dailyChallenge.name });
  const secondCard = page.getByRole('article', { name: weeklyChallenge.name });

  await firstCard.getByRole('button', { name: '했어요' }).click();
  await expect(firstCard.getByText('최신 진행 정보 확인 필요')).toBeVisible();
  await secondCard.getByRole('button', { name: '했어요' }).click();
  await expect(secondCard.getByText('최신 진행 정보 확인 필요')).toBeVisible();
  await expect(firstCard.getByText('최신 진행 정보 확인 필요')).toBeVisible();
  expect(verificationPosts).toBe(2);
});

test('a delayed My check-in does not refresh after leaving the page', async ({ page }) => {
  await authenticate(page);
  const before = participation();
  let challengeReads = 0;
  let badgeReads = 0;
  let releaseVerification!: () => void;
  let finishVerification!: () => void;
  const verificationGate = new Promise<void>(resolve => {
    releaseVerification = resolve;
  });
  const verificationFinished = new Promise<void>(resolve => {
    finishVerification = resolve;
  });
  await page.route('**/api/v1/user/challenges', route => {
    challengeReads += 1;
    return route.fulfill({ json: { items: [before], total_count: 1 } });
  });
  await page.route('**/api/v1/user/badges', route => {
    badgeReads += 1;
    return route.fulfill({ json: { items: [], total_count: 0 } });
  });
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: [dailyChallenge], total_count: 1, offset: 0, limit: 100 },
  }));
  await page.route('**/api/v1/user/challenges/501/verifications', async route => {
    await verificationGate;
    await route.fulfill({ status: 201, json: {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    } });
    finishVerification();
  });

  await page.goto('/challenges');
  await page.getByRole('article', { name: dailyChallenge.name }).getByRole('button', { name: '했어요' }).click();
  await page.getByRole('link', { name: '둘러보기', exact: true }).click();
  await expect(page.getByRole('region', { name: '챌린지 목록' })).toContainText(dailyChallenge.name);
  const readsBeforeRelease = { challengeReads, badgeReads };

  releaseVerification();
  await verificationFinished;
  await page.waitForTimeout(100);

  expect({ challengeReads, badgeReads }).toEqual(readsBeforeRelease);
  await expect(page).toHaveURL(/\/challenges\/browse$/);
});

test('SELF participation without a reward badge is labeled as direct verification', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page, {
    catalog: [weeklyChallenge],
    participations: [participation({
      challenge_id: weeklyChallenge.id,
      challenge_name: weeklyChallenge.name,
      challenge: { ...weeklyChallenge, can_join: false, participation_id: 501 },
    })],
    badges: [],
  });

  await page.goto('/challenges');

  const card = page.getByRole('article', { name: weeklyChallenge.name });
  await expect(card.getByText('직접 인증', { exact: true })).toBeVisible();
  await expect(card.getByText('공식 배지', { exact: true })).toHaveCount(0);
});

test('participation detail uses server dates, counts, progress, and verified dates', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation() }));

  await page.goto('/challenges/participations/501');

  await expect(page.getByRole('heading', { name: dailyChallenge.name })).toBeVisible();
  await expect(page.getByText('내 수행 기간 · 2026.9.8 ~ 2026.9.21')).toBeVisible();
  await expect(page.getByText('3 / 14일 인증', { exact: true })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: '내 인증 기록 진행률' })).toHaveAttribute('aria-valuenow', '21.43');
  await expect(page.getByLabel('2026-09-08 인증 완료')).toBeVisible();
  await expect(page.getByLabel('2026-09-10 미인증')).toBeVisible();
  await expect(page.getByRole('button', { name: '했어요' })).toBeEnabled();
});

test('active participation cancellation confirms retained history, posts once, and persists after reload', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  let cancelled = false;
  let cancelCalls = 0;
  let cancelBody: string | null = 'not-called';
  let cancelAuthorization: string | undefined;
  let releaseCancel!: () => void;
  const cancelGate = new Promise<void>(resolve => {
    releaseCancel = resolve;
  });
  const cancelledParticipation = participation({
    status: 'CANCELLED',
    cancelled_at: '2026-09-10T12:00:00+09:00',
    can_verify: false,
  });
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({
    json: cancelled ? cancelledParticipation : participation(),
  }));
  await page.route('**/api/v1/user/challenges/501/cancel', async route => {
    cancelCalls += 1;
    cancelBody = route.request().postData();
    cancelAuthorization = route.request().headers().authorization;
    await cancelGate;
    cancelled = true;
    await route.fulfill({ json: cancelledParticipation });
  });

  await page.goto('/challenges/participations/501');
  const cancelButton = page.getByRole('button', { name: '챌린지 참여 취소' });
  await expect(cancelButton).toBeVisible({ timeout: 2_000 });
  await cancelButton.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('기록은 보관');
  await expect(dialog).toContainText('모집 기간');
  // Each policy starts on its own line, even when there is room to run it inline.
  const policies = dialog.locator('[data-slot="dialog-description"] > span');
  await expect(policies).toHaveCount(3);
  for (const width of [320, 430]) {
    await page.setViewportSize({ width, height: 800 });
    const boxes = await policies.evaluateAll(elements => elements.map(element => {
      const { top, bottom, left, right } = element.getBoundingClientRect();
      return { top, bottom, left, right };
    }));
    for (let index = 0; index < boxes.length; index += 1) {
      expect(boxes[index].left).toBeGreaterThanOrEqual(0);
      expect(boxes[index].right).toBeLessThanOrEqual(width);
      if (index > 0) expect(boxes[index].top).toBeGreaterThan(boxes[index - 1].bottom);
    }
  }
  const confirm = dialog.getByRole('button', { name: '참여 취소', exact: true });
  await confirm.click();
  const cancelling = dialog.getByRole('button', { name: '취소 중...', exact: true });
  await expect(cancelling).toBeDisabled();
  await cancelling.evaluate((element: HTMLButtonElement) => element.click());
  expect(cancelCalls).toBe(1);

  releaseCancel();
  await expect(page.getByRole('heading', { name: '이번 도전은 여기까지예요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '챌린지 참여 취소' })).toHaveCount(0);
  expect(cancelCalls).toBe(1);
  expect(cancelBody).toBeNull();
  expect(cancelAuthorization).toBe('Bearer token-for-challenge-api@example.com');

  await page.reload();
  await expect(page.getByRole('heading', { name: '이번 도전은 여기까지예요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '챌린지 참여 취소' })).toHaveCount(0);
  expect(cancelCalls).toBe(1);
});

test('completed and expired participation details never offer cancellation', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  let status = 'ACTIVE';
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation({
    status,
    completed_at: status === 'COMPLETED' ? '2026-09-21T12:00:00+09:00' : null,
    can_verify: false,
  }) }));

  await page.goto('/challenges/participations/501');
  await expect(page.getByRole('button', { name: '챌린지 참여 취소' })).toBeVisible({ timeout: 2_000 });

  status = 'COMPLETED';
  await page.reload();
  await expect(page.getByRole('button', { name: '챌린지 참여 취소' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toHaveCount(0);

  status = 'EXPIRED';
  await page.reload();
  await expect(page.getByRole('heading', { name: '이번 도전은 여기까지예요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '챌린지 참여 취소' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '다시 참여하기', exact: true })).toHaveCount(0);
});

test('failed cancellation keeps the active participation and allows a deliberate retry', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation() }));
  let cancelCalls = 0;
  await page.route('**/api/v1/user/challenges/501/cancel', route => {
    cancelCalls += 1;
    return route.fulfill({ status: 409, json: {
      code: 'CHALLENGE_PERIOD_ENDED',
      message: '진행 중인 챌린지만 취소할 수 있어요.',
    } });
  });

  await page.goto('/challenges/participations/501');
  const cancelButton = page.getByRole('button', { name: '챌린지 참여 취소' });
  await expect(cancelButton).toBeVisible({ timeout: 2_000 });
  await cancelButton.click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: '참여 취소', exact: true }).click();

  await expect(dialog.getByRole('alert')).toContainText('진행 중인 챌린지만 취소할 수 있어요.');
  await expect(dialog.getByRole('button', { name: '참여 취소', exact: true })).toBeEnabled();
  expect(cancelCalls).toBe(1);
  await dialog.getByRole('button', { name: '돌아가기', exact: true }).click();
  await expect(page.getByRole('button', { name: '챌린지 참여 취소' })).toBeVisible();
  await expect(page.getByText('3 / 14일 인증', { exact: true })).toBeVisible();
});

test('cancellation authorization failure expires the session without showing stale cancelled state', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation() }));
  await page.route('**/api/v1/user/challenges/501/cancel', route => route.fulfill({
    status: 401,
    json: { code: 'UNAUTHORIZED', message: '로그인이 필요합니다.' },
  }));

  await page.goto('/challenges/participations/501');
  const cancelButton = page.getByRole('button', { name: '챌린지 참여 취소' });
  await expect(cancelButton).toBeVisible({ timeout: 2_000 });
  await cancelButton.click();
  await page.getByRole('dialog').getByRole('button', { name: '참여 취소', exact: true }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect.poll(() => page.evaluate(() => ({
    token: sessionStorage.getItem('poke.access-token'),
    principal: sessionStorage.getItem('poke.account-principal'),
  }))).toEqual({ token: null, principal: null });
  await expect(page.getByRole('heading', { name: '이번 도전은 여기까지예요' })).toHaveCount(0);
});

test('participation detail keeps a successful check-in when optional reads fail', async ({ page }) => {
  await authenticate(page);
  const before = participation();
  const after = participation({
    completed_count: 4,
    progress_rate: '28.57',
    can_verify: false,
    today_verification: {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    },
    verified_dates: ['2026-09-08', '2026-09-09', '2026-09-10'],
  });
  let checked = false;
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    status: 503,
    json: { code: 'TEMPORARY', message: '카탈로그를 불러오지 못했어요.' },
  }));
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({
    json: checked ? after : before,
  }));
  await page.route('**/api/v1/user/badges', route => {
    return checked
      ? route.fulfill({
        status: 503,
        json: { code: 'TEMPORARY', message: '배지 정보를 불러오지 못했어요.' },
      })
      : route.fulfill({ json: { items: [], total_count: 0 } });
  });
  await page.route('**/api/v1/user/challenges/501/verifications', route => {
    checked = true;
    return route.fulfill({ status: 201, json: after.today_verification });
  });

  await page.goto('/challenges/participations/501');
  await page.getByRole('button', { name: '했어요' }).click();

  await expect(page.getByRole('button', { name: '오늘 인증 완료' })).toBeDisabled();
  await expect(page.getByText('4 / 14일 인증', { exact: true })).toBeVisible();
  await expect(page.getByText('배지 정보를 불러오지 못했어요.')).toBeVisible();
  await expect(page.getByText('인증을 기록하지 못했어요.')).toHaveCount(0);
});

test('participation detail offers a GET-only retry when progress refresh fails after approval', async ({ page }) => {
  await authenticate(page);
  const before = participation();
  const after = participation({
    completed_count: 4,
    progress_rate: '28.57',
    can_verify: false,
    today_verification: {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    },
    verified_dates: ['2026-09-08', '2026-09-09', '2026-09-10'],
  });
  let checked = false;
  let refreshReads = 0;
  let verificationPosts = 0;
  await page.route('**/api/v1/user/challenges/501', route => {
    if (!checked) return route.fulfill({ json: before });
    refreshReads += 1;
    return refreshReads === 1
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '진행 정보를 불러오지 못했어요.' } })
      : route.fulfill({ json: after });
  });
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/challenges/501/verifications', route => {
    verificationPosts += 1;
    checked = true;
    return route.fulfill({ status: 201, json: after.today_verification });
  });

  await page.goto('/challenges/participations/501');
  await page.getByRole('button', { name: '했어요' }).click();

  await expect(page.getByRole('button', { name: '오늘 인증 완료' })).toBeDisabled();
  await expect(page.getByText('최신 진행 정보 확인 필요')).toBeVisible();
  await expect(page.getByText('3 / 14일 인증', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(page.getByText('4 / 14일 인증', { exact: true })).toBeVisible();
  await expect(page.getByText('최신 진행 정보 확인 필요')).toHaveCount(0);
  expect(verificationPosts).toBe(1);
});

test('a delayed check-in cannot overwrite another participation in the same account', async ({ page }) => {
  await authenticate(page);
  const second = participation({
    id: 502,
    challenge_id: weeklyChallenge.id,
    challenge_name: weeklyChallenge.name,
    challenge: { ...weeklyChallenge, can_join: false, participation_id: 502 },
  });
  let finishVerification!: () => void;
  const verificationGate = new Promise<void>(resolve => {
    finishVerification = resolve;
  });
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: participation() }));
  await page.route('**/api/v1/user/challenges/502', route => route.fulfill({ json: second }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/challenges/501/verifications', async route => {
    await verificationGate;
    await route.fulfill({ status: 201, json: {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    } });
  });

  await page.goto('/challenges/participations/501');
  await page.getByRole('button', { name: '했어요' }).click();
  await page.evaluate(() => {
    window.history.pushState({}, '', '/challenges/participations/502');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page.getByRole('heading', { name: weeklyChallenge.name })).toBeVisible();
  finishVerification();

  await page.waitForTimeout(100);
  await expect(page).toHaveURL(/\/challenges\/participations\/502$/);
  await expect(page.getByRole('heading', { name: weeklyChallenge.name })).toBeVisible();
  await expect(page.getByRole('heading', { name: dailyChallenge.name })).toHaveCount(0);
});

test('D30 WEEKLY_3 shows the full exclusive-end duration while keeping the last two days out of verification periods', async ({ page }) => {
  await authenticate(page);
  const weeklyThirty = {
    ...weeklyChallenge,
    period_code: 'D30',
    duration_days: 30,
  };
  const weeklyParticipation = participation({
    challenge_name: weeklyThirty.name,
    challenge: { ...weeklyThirty, can_join: false, participation_id: 503 },
    id: 503,
    started_at: '2026-09-01T00:00:00+09:00',
    end_at: '2026-10-01T00:00:00+09:00',
    target_count: 12,
    completed_count: 3,
    progress_rate: '25.00',
    today: '2026-09-29',
    can_verify: false,
    verified_dates: ['2026-09-02', '2026-09-09', '2026-09-16'],
    progress_periods: [
      { id: 811, period_start: '2026-09-01', period_end: '2026-09-07', target_count: 3, completed_count: 1, progress_rate: '33.33', is_completed: false, completed_at: null },
      { id: 812, period_start: '2026-09-08', period_end: '2026-09-14', target_count: 3, completed_count: 1, progress_rate: '33.33', is_completed: false, completed_at: null },
      { id: 813, period_start: '2026-09-15', period_end: '2026-09-21', target_count: 3, completed_count: 1, progress_rate: '33.33', is_completed: false, completed_at: null },
      { id: 814, period_start: '2026-09-22', period_end: '2026-09-28', target_count: 3, completed_count: 0, progress_rate: '0.00', is_completed: false, completed_at: null },
    ],
  });
  await page.route('**/api/v1/user/challenges/503', route => route.fulfill({ json: weeklyParticipation }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));

  await page.goto('/challenges/participations/503');

  await expect(page.getByText('내 수행 기간 · 2026.9.1 ~ 2026.9.30')).toBeVisible();
  await expect(page.getByText('수행 기간의 마지막 2일은 인증 집계 대상이 아니에요.')).toBeVisible();
  await expect(page.getByLabel('2026-09-28 미인증')).toBeVisible();
  await expect(page.getByLabel(/2026-09-29/)).toHaveCount(0);
});

test('invalid participation ids never issue detail or verification requests', async ({ page }) => {
  await authenticate(page);
  const challengeRequests: string[] = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path.includes('/api/v1/user/challenges/')) challengeRequests.push(path);
  });

  await page.goto('/challenges/participations/undefined');

  await expect(page.getByRole('heading', { name: '참여 기록을 찾을 수 없어요' })).toBeVisible();
  expect(challengeRequests).toEqual([]);
});

test('relative badge media paths resolve from the server root on every official badge surface', async ({ page }) => {
  await authenticate(page);
  const mediaBadge = { ...badge, image_path: 'media/badges/walk.png' };
  const mediaChallenge = { ...dailyChallenge, reward_badge: mediaBadge, can_join: false, participation_id: 501 };
  const awardedBadge = {
    id: 701,
    user_id: 7,
    badge_id: mediaBadge.id,
    challenge_id: mediaChallenge.id,
    user_challenge_id: 501,
    status: 'AWARDED',
    badge_name: mediaBadge.name,
    badge_image_path: 'media/badges/walk.png',
    awarded_at: '2026-09-07T12:00:00+09:00',
    revoked_at: null,
    revoke_reason: null,
  };
  const completed = participation({
    status: 'COMPLETED',
    completed_at: '2026-09-21T12:00:00+09:00',
    can_verify: false,
    challenge: mediaChallenge,
  });
  await stubChallengeReads(page, {
    catalog: [mediaChallenge],
    participations: [completed],
    badges: [awardedBadge],
  });
  await page.route('**/api/v1/user/challenge-catalog/101', route => route.fulfill({ json: mediaChallenge }));
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: completed }));
  await page.route('**/media/badges/walk.png', route => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
  }));

  const expectedPath = '/media/badges/walk.png';
  const surfaces = [
    { path: '/challenges/official/101', name: mediaBadge.name },
    { path: '/challenges/participations/501', name: mediaBadge.name },
    { path: '/challenges', name: mediaBadge.name },
    { path: '/challenges/badges', name: mediaBadge.name },
    { path: `/challenges/badges/${mediaBadge.id}`, name: mediaBadge.name },
  ];

  for (const surface of surfaces) {
    await page.goto(surface.path);
    await expect(page.getByRole('img', { name: surface.name }).first()).toHaveAttribute('src', expectedPath);
  }
});

test('badge box unions catalog and server awards, grays out unearned badges, and has no filters', async ({ page }) => {
  await authenticate(page);
  const awardedBadge = {
    id: 701,
    user_id: 7,
    badge_id: 99,
    challenge_id: 109,
    user_challenge_id: 599,
    status: 'AWARDED',
    badge_name: '서버 완주 배지',
    badge_image_path: '/images/challenges/badge-review.png',
    awarded_at: '2026-09-07T12:00:00+09:00',
    revoked_at: null,
    revoke_reason: null,
  };
  const revokedCatalogBadge = {
    ...awardedBadge,
    id: 702,
    badge_id: badge.id,
    challenge_id: dailyChallenge.id,
    badge_name: badge.name,
    badge_image_path: badge.image_path,
    status: 'REVOKED',
    revoked_at: '2026-09-08T12:00:00+09:00',
    revoke_reason: '운영자 회수',
  };
  await stubChallengeReads(page, {
    catalog: [dailyChallenge],
    badges: [awardedBadge, revokedCatalogBadge],
  });

  await page.goto('/challenges/badges');

  const grid = page.getByRole('list', { name: '챌린지 배지' });
  await expect(grid.getByRole('listitem')).toHaveCount(2);
  await expect(grid.getByRole('link', { name: `${badge.name}, 미획득` })).toBeVisible();
  await expect(grid.getByRole('link', { name: '서버 완주 배지, 1회 획득' })).toBeVisible();
  await expect(grid.getByRole('img', { name: badge.name })).toHaveClass(/grayscale/);
  await expect(page.getByRole('button', { name: /^(전체|기본|공식)$/ })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: /^(전체|기본|공식)$/ })).toHaveCount(0);

  await grid.getByRole('link', { name: `${badge.name}, 미획득` }).click();
  await expect(page.getByRole('heading', { name: '배지 상세' })).toBeVisible();
  await expect(page.getByText('아직 획득하지 않았어요.')).toBeVisible();
  await expect(page.getByText(badge.description)).toBeVisible();
});

test('authenticated home renders a server-backed challenge summary with navigation only', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: { code: 'NOT_FOUND', message: '없음' } }));
  await page.route('**/api/v1/medications', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/user-suppl-nutr?*', route => route.fulfill({ json: {
    items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null,
  } }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: {
    items: [participation()], total_count: 1,
  } }));

  await page.goto('/home');

  const summary = page.getByRole('region', { name: '챌린지' });
  await expect(summary.getByRole('link', { name: /매일 30분 걷기.*21.43%/ })).toBeVisible();
  await expect(summary.getByText('예시 데이터')).toHaveCount(0);
  await expect(summary.getByRole('button', { name: /했어요/ })).toHaveCount(0);
  await summary.getByRole('link', { name: /매일 30분 걷기.*21.43%/ }).click();
  await expect(page).toHaveURL(/\/challenges\/participations\/501$/);
});

for (const width of [320, 430]) {
  test(`home challenge density shows every active row and grows naturally at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate(page);
    const mutations: string[] = [];
    page.on('request', request => {
      if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) mutations.push(request.url());
    });
    await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: {} }));
    await page.route('**/api/v1/medications', route => route.fulfill({ json: [] }));
    let items = [participation()];
    await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items, total_count: items.length } }));
    await page.goto('/home');
    const summary = page.getByRole('region', { name: '챌린지', exact: true });
    const rows = summary.getByRole('link', { name: /상세 보기$/ });
    await expect(rows).toHaveCount(1);
    const card = rows.first().locator('..');
    const singleHeight = (await card.boundingBox())!.height;
    // One short row should not reserve the previous two-row minimum height.
    expect.soft(singleHeight).toBeLessThan(110);
    const shortTitleRight = await rows.first().getByText('매일 30분 걷기', { exact: true }).evaluate(el => {
      const textRange = document.createRange();
      textRange.selectNodeContents(el);
      return textRange.getBoundingClientRect().right;
    });
    const typeBadgeBounds = (await rows.first().getByText('공식', { exact: true }).boundingBox())!;
    expect(typeBadgeBounds.x - shortTitleRight).toBeLessThanOrEqual(16);
    await summary.screenshot({ path: testInfo.outputPath(`home-challenge-one-${width}.png`) });
    items = [participation(), participation({ id: 502, challenge_name: '물 마시기' }),
      participation({ id: 503, challenge_name: '가벼운 스트레칭' }),
      participation({ id: 504, challenge_name: '취소한 도전', status: 'CANCELLED' }),
      participation({ id: 505, challenge_name: '완료한 도전', status: 'COMPLETED' }),
      participation({ id: 506, challenge_name: '만료한 도전', status: 'EXPIRED' })];
    await page.reload();
    await expect(rows).toHaveCount(3);
    await expect(summary.getByText(/취소한 도전|완료한 도전|만료한 도전/)).toHaveCount(0);
    await expect(rows.nth(2)).toHaveAttribute('href', '/challenges/participations/503');
    expect((await card.boundingBox())!.height).toBeGreaterThan(singleHeight + 80);
    await summary.screenshot({ path: testInfo.outputPath(`home-challenge-three-${width}.png`) });
    expect(mutations).toEqual([]);
  });

  test(`home challenge type stays visible beside a wrapping title at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate(page);
    await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: {} }));
    await page.route('**/api/v1/medications', route => route.fulfill({ json: [] }));
    const title = '매일건강한습관으로몸과마음을돌보는아주긴공식챌린지이름'.repeat(3);
    await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: {
      items: [participation({ challenge_name: title })], total_count: 1,
    } }));
    await page.goto('/home');
    const summary = page.getByRole('region', { name: '챌린지', exact: true });
    const row = summary.getByRole('link', { name: /상세 보기$/ });
    await expect(row.getByText('공식', { exact: true })).toBeVisible();
    const name = row.getByText(title, { exact: true });
    expect(await name.evaluate(el => el.clientHeight >= parseFloat(getComputedStyle(el).lineHeight) * 2)).toBe(true);
    expect(await row.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    const bounds = (await row.boundingBox())!;
    const badgeBounds = (await row.getByText('공식', { exact: true }).boundingBox())!;
    expect(badgeBounds.x + badgeBounds.width).toBeLessThanOrEqual(bounds.x + bounds.width);
    await summary.screenshot({ path: testInfo.outputPath(`home-challenge-long-${width}.png`) });
  });
}

test('home challenge summary stays available when medication loading fails', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: { code: 'NOT_FOUND', message: '없음' } }));
  await page.route('**/api/v1/medications', route => route.fulfill({ status: 503, json: {
    code: 'TEMPORARY', message: '복약 서버를 확인해주세요.',
  } }));
  await page.route('**/api/v1/med/user-suppl-nutr?*', route => route.fulfill({ json: {
    items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null,
  } }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: {
    items: [participation()], total_count: 1,
  } }));

  await page.goto('/home');

  await expect(page.getByText('복약 서버를 확인해주세요.')).toBeVisible();
  await expect(page.getByRole('region', { name: '챌린지' }).getByRole('link', { name: /매일 30분 걷기.*21.43%/ })).toBeVisible();
});

test('unfinished personal creation route shows a clear coming-soon state', async ({ page }) => {
  await authenticate(page);
  const mutations: string[] = [];
  page.on('request', request => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) mutations.push(request.url());
  });

  await page.goto('/challenges/create');
  await expect(page.getByRole('heading', { name: '준비 중이에요' })).toBeVisible();
  await expect(page.getByText('#315에서 제공할 예정이에요.')).toBeVisible();
  await expect(page.getByText('감기약', { exact: true })).toHaveCount(0);
  expect(mutations).toEqual([]);
});

test('catalog load failure never falls back to mock data and recovers on reload action', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page);
  let reads = 0;
  await page.route('**/api/v1/user/challenge-catalog?*', route => {
    reads += 1;
    return reads <= 2
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '공식 챌린지 서버를 확인해주세요.' } })
      : route.fulfill({ json: { items: [dailyChallenge], total_count: 1, offset: 0, limit: 100 } });
  });

  await page.goto('/challenges/browse');
  await expect(page.getByRole('alert')).toContainText('공식 챌린지 서버를 확인해주세요.');
  await expect(page.getByText('물 마시기', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(page.getByRole('button', { name: /매일 30분 걷기.*자세히 보기/ })).toBeVisible();
  expect(reads).toBeGreaterThanOrEqual(3);
});

test('empty My state directs users to official browse without inventing tailored data', async ({ page }) => {
  await authenticate(page);
  await stubChallengeReads(page, { catalog: [], participations: [], badges: [] });
  await page.goto('/challenges');

  await expect(page.getByText('참여 중인 챌린지가 없어요.')).toBeVisible();
  await expect(page.getByRole('link', { name: '둘러보기', exact: true })).toHaveAttribute('href', '/challenges/browse');
  await expect(page.getByText('감기약', { exact: true })).toHaveCount(0);
});

test('browse to join to My check-in persists after reload through server reads', async ({ page }) => {
  await authenticate(page);
  let joined = false;
  let checked = false;
  const authorizations: Array<string | undefined> = [];
  const currentParticipation = () => participation({
    completed_count: checked ? 4 : 3,
    progress_rate: checked ? '28.57' : '21.43',
    can_verify: !checked,
    today_verification: checked ? {
      id: 901,
      user_challenge_id: 501,
      progress_id: 801,
      verification_date: '2026-09-10',
      content: null,
      image_path: null,
      status: 'APPROVED',
      rejection_reason: null,
      reviewed_by_admin_id: null,
      reviewed_at: '2026-09-10T11:00:00+09:00',
      submitted_at: '2026-09-10T11:00:00+09:00',
    } : null,
    verified_dates: checked ? ['2026-09-08', '2026-09-09', '2026-09-10'] : ['2026-09-08', '2026-09-09'],
  });
  await page.route('**/api/v1/user/challenge-catalog?*', route => {
    authorizations.push(route.request().headers().authorization);
    const item = { ...dailyChallenge, can_join: !joined, participation_id: joined ? 501 : null };
    return route.fulfill({ json: { items: [item], total_count: 1, offset: 0, limit: 100 } });
  });
  await page.route('**/api/v1/user/challenge-catalog/101', route => route.fulfill({ json: {
    ...dailyChallenge, can_join: !joined, participation_id: joined ? 501 : null,
  } }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: {
    items: joined ? [currentParticipation()] : [], total_count: joined ? 1 : 0,
  } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/challenges/101/join', route => {
    joined = true;
    return route.fulfill({ status: 201, json: currentParticipation() });
  });
  await page.route('**/api/v1/user/challenges/501', route => route.fulfill({ json: currentParticipation() }));
  await page.route('**/api/v1/user/challenges/501/verifications', route => {
    checked = true;
    return route.fulfill({ status: 201, json: currentParticipation().today_verification });
  });

  await page.goto('/challenges/browse');
  await page.getByRole('button', { name: /매일 30분 걷기.*자세히 보기/ }).click();
  await page.getByRole('button', { name: '참여하기' }).click();
  await expect(page).toHaveURL(/\/challenges\/participations\/501$/);
  await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '챌린지', exact: true }).click();
  const card = page.getByRole('article', { name: dailyChallenge.name });
  await card.getByRole('button', { name: '했어요' }).click();
  await expect(card.getByText('4 / 14일 인증')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('article', { name: dailyChallenge.name }).getByText('4 / 14일 인증')).toBeVisible();
  expect(joined).toBe(true);
  expect(checked).toBe(true);
  expect(authorizations.every(value => value === 'Bearer token-for-challenge-api@example.com')).toBe(true);
});

test('a delayed previous-account response cannot replace the current account challenge list', async ({ page }) => {
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('poke.account-principal')) {
      sessionStorage.setItem('poke.access-token', 'token-for-account-a@example.com');
      sessionStorage.setItem('poke.account-principal', 'account-a@example.com');
    }
  });
  let releaseAccountA!: () => void;
  const accountAGate = new Promise<void>(resolve => {
    releaseAccountA = resolve;
  });
  const accountAParticipation = participation({
    challenge_name: '첫 계정 챌린지',
    challenge: { ...dailyChallenge, name: '첫 계정 챌린지' },
  });
  const accountBParticipation = participation({
    id: 502,
    challenge_name: '둘째 계정 챌린지',
    challenge: { ...dailyChallenge, id: 104, name: '둘째 계정 챌린지' },
  });
  await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: { code: 'NOT_FOUND', message: '없음' } }));
  await page.route('**/api/v1/auth/login', route => route.fulfill({ json: { access_token: 'token-b' } }));
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: {
    items: [dailyChallenge], total_count: 1, offset: 0, limit: 100,
  } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/challenges', async route => {
    if (route.request().headers().authorization === 'Bearer token-for-account-a@example.com') {
      await accountAGate;
      await route.fulfill({ json: { items: [accountAParticipation], total_count: 1 } });
      return;
    }
    await route.fulfill({ json: { items: [accountBParticipation], total_count: 1 } });
  });

  await page.goto('/challenges');
  await expect(page.getByRole('status', { name: '내 챌린지 불러오는 중' })).toBeVisible();
  await page.goto('/login');
  await page.getByLabel('이메일').fill('account-b@example.com');
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await expect(page).toHaveURL(/\/home$/);
  await page.goto('/challenges');
  await expect(page.getByRole('article', { name: '둘째 계정 챌린지' })).toBeVisible();
  releaseAccountA();
  await page.waitForTimeout(100);
  await expect(page.getByRole('article', { name: '첫 계정 챌린지' })).toHaveCount(0);
  await expect(page.getByRole('article', { name: '둘째 계정 챌린지' })).toBeVisible();
});
