import { expect, test, type Page, type Route } from 'playwright/test';

test.setTimeout(60_000);

const TODAY = '2026-09-09';

const officialBadge = {
  id: 31,
  name: '튼튼 걷기 배지',
  description: '꾸준한 걷기를 기록했어요.',
  image_path: '/images/challenges/badge-walk.png',
};

const officialChallenge = {
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
  reward_badge: officialBadge,
  can_join: false,
  participation_id: 501,
};

function officialParticipation(overrides: Record<string, unknown> = {}) {
  return {
    id: 501,
    user_id: 7,
    challenge_id: 101,
    challenge_name: officialChallenge.name,
    status: 'ACTIVE',
    joined_at: '2026-09-01T09:00:00+09:00',
    started_at: '2026-09-01T00:00:00+09:00',
    end_at: '2026-09-15T00:00:00+09:00',
    target_count: 14,
    completed_count: 3,
    progress_rate: '21.43',
    completed_at: null,
    cancelled_at: null,
    progress_periods: [{
      id: 801,
      period_start: '2026-09-01',
      period_end: '2026-09-14',
      target_count: 14,
      completed_count: 3,
      progress_rate: '21.43',
      is_completed: false,
      completed_at: null,
    }],
    challenge: officialChallenge,
    today: TODAY,
    today_verification: null,
    can_verify: true,
    verified_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
    ...overrides,
  };
}

function customParticipation(overrides: Record<string, unknown> = {}) {
  return {
    id: 701,
    templateId: 31,
    challengeType: 'MEDICATION',
    challengeName: '처방 일정 지키기',
    status: 'ACTIVE',
    joinedAt: '2026-09-01T09:00:00+09:00',
    endAt: '2026-09-15T00:00:00+09:00',
    actualEndDate: '2026-09-14',
    targetCount: 14,
    completedCount: 2,
    progressRate: '14.29',
    action: 'NONE',
    targets: [{ id: 801, sourceId: 12, name: '서울의원 처방' }],
    occurrences: [{
      id: 901,
      targetId: 801,
      scheduledDate: TODAY,
      slot: 'MORNING',
      scheduledAt: `${TODAY}T08:00:00+09:00`,
      isCompleted: false,
    }],
    ...overrides,
  };
}

function medicationOverview(recordId: number, alias: string) {
  return {
    recordId,
    alias,
    documentImageUrl: '/mock/medication-envelope.svg',
    start: { date: TODAY, slot: 'morning' },
    endDate: '2026-09-16',
    daysRemaining: 7,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
    medications: [{
      medicationId: recordId * 10,
      name: `${alias} 약`,
      dose: '1정',
      days: 7,
      daysRemaining: 7,
      slots: ['morning'],
      asNeeded: false,
    }],
  };
}

const supplement = {
  id: 501,
  custom_name: '오메가3',
  dose_amount: '1.000',
  dose_unit: '정',
  start_date: TODAY,
  end_date: null,
  status: 'ACTIVE',
  score: null,
  review_body: null,
  note: null,
  created_at: `${TODAY}T09:00:00+09:00`,
  updated_at: null,
  slots: [{ slot: 'MORNING', time: '07:30:00' }],
  supplement: null,
};

interface StubReply {
  status?: number;
  json: unknown;
}

interface HomeStubOptions {
  official?: (read: number) => StubReply | Promise<StubReply>;
  custom?: (read: number) => StubReply | Promise<StubReply>;
  medications?: unknown[];
  supplements?: unknown[];
  saveMedication?: (payload: Record<string, unknown>, write: number) => StubReply;
  saveSupplement?: (payload: Record<string, unknown>, write: number) => StubReply;
}

async function fulfill(route: Route, reply: StubReply) {
  await route.fulfill({ status: reply.status ?? 200, json: reply.json });
}

async function authenticate(page: Page, principal = 'home-progress@example.com') {
  await page.addInitScript(({ principal }) => {
    sessionStorage.setItem('poke.access-token', `token-for-${principal}`);
    sessionStorage.setItem('poke.account-principal', principal);
  }, { principal });
}

async function stubHome(page: Page, options: HomeStubOptions = {}) {
  await page.clock.setFixedTime(new Date(`${TODAY}T12:00:00+09:00`));
  await authenticate(page);
  const counts = {
    officialReads: 0,
    customReads: 0,
    customMutations: 0,
    medicationWrites: [] as Array<Record<string, unknown>>,
    supplementWrites: [] as Array<Record<string, unknown>>,
  };

  await page.route('**/api/v1/**', route => route.fulfill({
    status: 404,
    json: { code: 'NOT_FOUND', message: '이 테스트에서 지정하지 않은 요청입니다.' },
  }));
  await page.route('**/api/v1/display/med/nutr/rank*', route => route.fulfill({ status: 204 }));
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, route => route.fulfill({
    json: options.medications ?? [],
  }));
  await page.route('**/api/v1/medications/doses*', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: [] });
      return;
    }
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    counts.medicationWrites.push(payload);
    await fulfill(
      route,
      options.saveMedication?.(payload, counts.medicationWrites.length) ?? { json: payload },
    );
  });
  await page.route('**/api/v1/med/user-suppl-nutr*', route => route.fulfill({ json: {
    items: options.supplements ?? [],
    total: options.supplements?.length ?? 0,
    offset: 0,
    limit: 100,
    nutrient_standard: null,
  } }));
  await page.route('**/api/v1/med/supplement-doses*', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: [] });
      return;
    }
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    counts.supplementWrites.push(payload);
    await fulfill(
      route,
      options.saveSupplement?.(payload, counts.supplementWrites.length) ?? { json: payload },
    );
  });
  await page.route('**/api/v1/user/challenges', async route => {
    counts.officialReads += 1;
    await fulfill(
      route,
      await (options.official?.(counts.officialReads) ?? { json: { items: [], total_count: 0 } }),
    );
  });
  await page.route('**/api/v1/user/custom-challenge-participations', async route => {
    if (route.request().method() !== 'GET') {
      counts.customMutations += 1;
      await route.fulfill({ status: 405, json: { code: 'METHOD_NOT_ALLOWED' } });
      return;
    }
    counts.customReads += 1;
    await fulfill(
      route,
      await (options.custom?.(counts.customReads) ?? { json: { items: [], totalCount: 0 } }),
    );
  });
  page.on('request', request => {
    if (
      request.url().includes('/custom-challenge')
      && request.method() !== 'GET'
    ) counts.customMutations += 1;
  });
  return counts;
}

test('홈은 맞춤 진행률을 서버 값으로 표시하고 공식 빈 상태와 모순시키지 않는다', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  const longName = `아주 긴 맞춤 챌린지 이름 ${'꾸준한건강습관'.repeat(8)}`;
  const custom = [
    customParticipation({ challengeName: longName }),
    customParticipation({
      id: 702,
      challengeName: '아직 예정이 없는 챌린지',
      targetCount: 0,
      completedCount: 0,
      progressRate: '100.00',
      occurrences: [],
    }),
    customParticipation({ id: 703, challengeName: '세 번째 맞춤 챌린지' }),
  ];
  const counts = await stubHome(page, {
    official: () => ({ json: { items: [], total_count: 0 } }),
    custom: () => ({ json: { items: custom, totalCount: custom.length } }),
  });

  await page.goto('/home');

  const summary = page.getByRole('region', { name: '챌린지' });
  const customSection = summary.getByRole('region', { name: '맞춤 챌린지' });
  await expect(customSection.getByRole('heading', { name: '맞춤 챌린지 · 진행 중 3개' }))
    .toBeVisible();
  await expect(customSection.getByRole('link')).toHaveCount(2);
  await expect(customSection.getByText('세 번째 맞춤 챌린지')).toHaveCount(0);
  await expect(summary.getByText('참여 중인 챌린지가 없어요')).toHaveCount(0);

  const longTitle = customSection.getByText(longName, { exact: true });
  await expect(longTitle).toBeVisible();
  await expect(longTitle).toHaveCSS('overflow-wrap', 'anywhere');
  expect(await longTitle.evaluate(element => element.scrollWidth <= element.clientWidth + 1))
    .toBe(true);

  const zeroTarget = customSection.getByRole('link', { name: /아직 예정이 없는 챌린지/ });
  await expect(zeroTarget).toContainText('0 / 0회');
  await expect(zeroTarget).toContainText('예정된 목표 없음');
  await expect(zeroTarget.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  await expect(zeroTarget).not.toContainText('100%');
  await expect(customSection.getByText(/배지|달성/)).toHaveCount(0);
  expect(counts.customMutations).toBe(0);
});

test('공식 조회의 loading과 error는 맞춤 카드와 재조회를 가리지 않는다', async ({ page }) => {
  let releaseOfficial!: () => void;
  const officialGate = new Promise<void>(resolve => { releaseOfficial = resolve; });
  let officialRecovered = false;
  const counts = await stubHome(page, {
    official: async () => {
      if (!officialRecovered) {
        await officialGate;
        return { status: 503, json: { code: 'TEMPORARY', message: '공식 요약을 불러오지 못했어요.' } };
      }
      return { json: { items: [officialParticipation()], total_count: 1 } };
    },
    custom: () => ({ json: { items: [customParticipation()], totalCount: 1 } }),
  });

  await page.goto('/home');
  const summary = page.getByRole('region', { name: '챌린지' });
  const officialSection = summary.getByRole('region', { name: '공식 챌린지' });
  const customSection = summary.getByRole('region', { name: '맞춤 챌린지' });
  await expect(officialSection.getByRole('status', { name: '공식 챌린지 요약 불러오는 중' }))
    .toBeVisible();
  await expect(customSection.getByText('처방 일정 지키기')).toBeVisible();

  releaseOfficial();
  await expect(officialSection.getByRole('alert')).toContainText('공식 요약을 불러오지 못했어요.');
  const officialReadsBeforeRetry = counts.officialReads;
  const customReadsBeforeRetry = counts.customReads;
  officialRecovered = true;
  await officialSection.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(officialSection.getByText('매일 30분 걷기')).toBeVisible();
  await expect(customSection.getByText('처방 일정 지키기')).toBeVisible();
  expect(counts.officialReads).toBe(officialReadsBeforeRetry + 1);
  expect(counts.customReads).toBe(customReadsBeforeRetry);
  expect(counts.customMutations).toBe(0);
});

test('맞춤 조회 실패와 재시도는 공식 카드와 공식 조회 횟수에 영향을 주지 않는다', async ({
  page,
}) => {
  let customRecovered = false;
  const counts = await stubHome(page, {
    official: () => ({ json: { items: [officialParticipation()], total_count: 1 } }),
    custom: () => customRecovered
      ? ({ json: { items: [customParticipation()], totalCount: 1 } })
      : ({ status: 500, json: { code: 'TEMPORARY', message: '맞춤 요약을 불러오지 못했어요.' } }),
  });

  await page.goto('/home');
  const summary = page.getByRole('region', { name: '챌린지' });
  const officialSection = summary.getByRole('region', { name: '공식 챌린지' });
  const customSection = summary.getByRole('region', { name: '맞춤 챌린지' });
  await expect(officialSection.getByText('매일 30분 걷기')).toBeVisible();
  await expect(customSection.getByRole('alert')).toContainText('맞춤 요약을 불러오지 못했어요.');

  const officialReadsBeforeRetry = counts.officialReads;
  const customReadsBeforeRetry = counts.customReads;
  customRecovered = true;
  await customSection.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(customSection.getByText('처방 일정 지키기')).toBeVisible();
  await expect(officialSection.getByText('매일 30분 걷기')).toBeVisible();
  expect(counts.customReads).toBe(customReadsBeforeRetry + 1);
  expect(counts.officialReads).toBe(officialReadsBeforeRetry);
  expect(counts.customMutations).toBe(0);
});

test('복약 저장 성공과 되돌리기는 맞춤 진행률을 각각 한 번 다시 조회한다', async ({ page }) => {
  let completedCount = 2;
  const counts = await stubHome(page, {
    medications: [medicationOverview(12, '서울의원 처방')],
    official: () => ({ json: { items: [officialParticipation()], total_count: 1 } }),
    custom: () => ({
      json: {
        items: [customParticipation({
          completedCount,
          progressRate: completedCount === 3 ? '21.43' : '14.29',
        })],
        totalCount: 1,
      },
    }),
    saveMedication: payload => {
      completedCount = payload.taken ? 3 : 2;
      return { json: payload };
    },
  });

  await page.goto('/home');
  const customSection = page.getByRole('region', { name: '맞춤 챌린지' });
  await expect(customSection.getByText('2 / 14회')).toBeVisible();
  const initialCustomReads = counts.customReads;

  await page.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect(customSection.getByText('3 / 14회')).toBeVisible();
  expect(counts.customReads).toBe(initialCustomReads + 1);

  await page.getByRole('button', { name: '되돌리기', exact: true }).click();
  await expect(customSection.getByText('2 / 14회')).toBeVisible();
  expect(counts.customReads).toBe(initialCustomReads + 2);
  expect(counts.medicationWrites.map(item => item.taken)).toEqual([true, false]);
  expect(counts.customMutations).toBe(0);
});

test('복약 저장이 모두 실패하면 재조회하지 않고 부분 성공하면 한 번만 재조회한다', async ({
  page,
}) => {
  let phase: 'all-fail' | 'partial' = 'all-fail';
  let completedCount = 2;
  const counts = await stubHome(page, {
    medications: [
      medicationOverview(12, '서울의원 처방'),
      medicationOverview(24, '튼튼병원 처방'),
    ],
    official: () => ({ json: { items: [], total_count: 0 } }),
    custom: () => ({
      json: {
        items: [customParticipation({
          completedCount,
          progressRate: completedCount === 2 ? '14.29' : '21.43',
        })],
        totalCount: 1,
      },
    }),
    saveMedication: payload => {
      if (phase === 'all-fail' || payload.recordId === 24) {
        return { status: 503, json: { code: 'TEMPORARY', message: '저장 실패' } };
      }
      completedCount = 3;
      return { json: payload };
    },
  });

  await page.goto('/home');
  await expect(page.getByRole('region', { name: '맞춤 챌린지' }).getByText('2 / 14회'))
    .toBeVisible();
  const initialCustomReads = counts.customReads;
  await page.getByRole('button', { name: '먹었어요', exact: true }).click();
  await expect(
    page.getByRole('dialog').getByRole('heading', { name: '기록하지 못했어요' }),
  ).toBeVisible();
  await page.waitForTimeout(100);
  expect(counts.customReads).toBe(initialCustomReads);

  phase = 'partial';
  await page.getByRole('dialog').getByRole('button', { name: '다시 시도' }).click();
  await expect.poll(() => counts.customReads).toBe(initialCustomReads + 1);
  expect(counts.customMutations).toBe(0);
});

test('영양제 저장 실패는 재조회하지 않고 재시도 성공과 되돌리기는 각각 재조회한다', async ({
  page,
}) => {
  let failNext = true;
  let completedCount = 2;
  const counts = await stubHome(page, {
    supplements: [supplement],
    official: () => ({ json: { items: [], total_count: 0 } }),
    custom: () => ({
      json: {
        items: [customParticipation({
          challengeType: 'SUPPLEMENT',
          completedCount,
          progressRate: completedCount === 3 ? '21.43' : '14.29',
        })],
        totalCount: 1,
      },
    }),
    saveSupplement: payload => {
      if (failNext) {
        failNext = false;
        return { status: 503, json: { code: 'TEMPORARY', message: '저장 실패' } };
      }
      completedCount = payload.taken ? 3 : 2;
      return { json: payload };
    },
  });

  await page.goto('/home');
  const customSection = page.getByRole('region', { name: '맞춤 챌린지' });
  await expect(customSection.getByText('2 / 14회')).toBeVisible();
  const initialCustomReads = counts.customReads;
  await page.getByRole('tab', { name: '오늘의 영양제' }).click();
  const supplementGroup = page.getByRole('group', { name: '아침 영양제' });
  await supplementGroup.getByRole('button', { name: '오메가3 선택' }).click();
  await supplementGroup.getByRole('button', { name: '1개 먹었어요' }).click();
  await expect(supplementGroup.getByRole('alert')).toBeVisible();
  await page.waitForTimeout(100);
  expect(counts.customReads).toBe(initialCustomReads);

  await supplementGroup.getByRole('button', { name: '다시 시도' }).click();
  await expect(customSection.getByText('3 / 14회')).toBeVisible();
  expect(counts.customReads).toBe(initialCustomReads + 1);

  await supplementGroup.getByRole('button', { name: '오메가3 복용 완료' }).click();
  await supplementGroup.getByRole('button', { name: '1개 되돌리기' }).click();
  await expect(customSection.getByText('2 / 14회')).toBeVisible();
  expect(counts.customReads).toBe(initialCustomReads + 2);
  expect(counts.supplementWrites.map(item => item.taken)).toEqual([true, true, false]);
  expect(counts.customMutations).toBe(0);
});

test('무효화 전에 시작한 늦은 맞춤 응답은 최신 진행률을 덮어쓰지 않는다', async ({ page }) => {
  let saved = false;
  let releaseInitialReads!: () => void;
  const initialReadsGate = new Promise<void>(resolve => { releaseInitialReads = resolve; });
  const counts = await stubHome(page, {
    medications: [medicationOverview(12, '서울의원 처방')],
    official: () => ({ json: { items: [], total_count: 0 } }),
    custom: async () => {
      if (!saved) {
        await initialReadsGate;
        return { json: {
          items: [customParticipation({ completedCount: 1, progressRate: '7.14' })],
          totalCount: 1,
        } };
      }
      return { json: {
        items: [customParticipation({ completedCount: 7, progressRate: '50.00' })],
        totalCount: 1,
      } };
    },
    saveMedication: payload => {
      saved = true;
      return { json: payload };
    },
  });

  await page.goto('/home');
  await expect(
    page.getByRole('region', { name: '맞춤 챌린지' }).getByRole('status'),
  ).toBeVisible();
  await page.getByRole('button', { name: '먹었어요', exact: true }).click();
  const customSection = page.getByRole('region', { name: '맞춤 챌린지' });
  await expect(customSection.getByText('7 / 14회')).toBeVisible();
  const readsAfterInvalidation = counts.customReads;

  releaseInitialReads();
  await page.waitForTimeout(100);
  await expect(customSection.getByText('7 / 14회')).toBeVisible();
  await expect(customSection.getByText('1 / 14회')).toHaveCount(0);
  expect(counts.customReads).toBe(readsAfterInvalidation);
  expect(counts.customMutations).toBe(0);
});
