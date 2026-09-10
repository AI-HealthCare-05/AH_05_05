import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(120_000);
test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  page.setDefaultTimeout(5_000);
  page.setDefaultNavigationTimeout(60_000);
});

function recordsForDate(page: Page, date: string) {
  const [, month, day] = date.split('-').map(Number);
  return page.getByRole('region', { name: '챌린지 달력', exact: true })
    .filter({ has: page.getByRole('heading', { name: `${month}월 ${day}일`, exact: true }) })
    .getByRole('region', { name: '날짜별 복용 기록' });
}

const medicationA = {
  templateId: 31,
  challengeType: 'MEDICATION',
  challengeName: '처방 일정 지키기',
  rewardBadge: {
    id: 9,
    name: '복약 루틴 배지',
    description: '처방 일정 달성 배지',
    imagePath: '/media/badges/medication-routine.png',
  },
  action: 'NONE',
  targets: [
    { id: 101, name: '서울의원 1차 처방', existingParticipationId: null },
    { id: 102, name: '튼튼병원 2차 처방', existingParticipationId: null },
  ],
};

const medicationB = {
  ...medicationA,
  templateId: 32,
  challengeName: '저녁 처방 잊지 않기',
};

const supplement = {
  templateId: 41,
  challengeType: 'SUPPLEMENT',
  challengeName: '영양제 루틴 이어가기',
  rewardBadge: null,
  action: 'NONE',
  targets: [
    { id: 203, name: '비타민D', existingParticipationId: 880 },
    { id: 201, name: '오메가3', existingParticipationId: null },
    { id: 202, name: '유산균', existingParticipationId: null },
  ],
};

function participation(overrides: Record<string, unknown> = {}) {
  const completedCount = Number(overrides.completedCount ?? 5);
  return {
    id: 701,
    templateId: 31,
    challengeType: 'MEDICATION',
    challengeName: medicationA.challengeName,
    rewardBadge: medicationA.rewardBadge,
    status: 'ACTIVE',
    joinedAt: '2026-09-09T07:00:00+09:00',
    endAt: '2026-09-16T09:00:00+09:00',
    actualEndDate: '2026-09-16',
    targetCount: 14,
    completedCount: 5,
    progressRate: '35.71',
    // Explicit calendar fixtures exercise old API fallback from their own occurrences.
    ...('occurrences' in overrides ? {} : {
      targetDayCount: 7,
      completedDayCount: Math.floor(completedCount / 2),
      dayProgressRate: (Math.floor(completedCount / 2) * 100 / 7).toFixed(2),
    }),
    action: 'NONE',
    targets: [{ id: 801, sourceId: 101, name: '서울의원 1차 처방' }],
    occurrences: Array.from({ length: 14 }, (_, index) => ({
      id: 901 + index,
      targetId: 801,
      scheduledDate: `2026-09-${String(9 + Math.floor(index / 2)).padStart(2, '0')}`,
      slot: index % 2 === 0 ? 'MORNING' : 'EVENING',
      scheduledAt: `2026-09-${String(9 + Math.floor(index / 2)).padStart(2, '0')}T${index % 2 === 0 ? '08' : '19'}:00:00+09:00`,
      isCompleted: index < completedCount,
    })),
    ...overrides,
  };
}

async function authenticate(page: Page, principal = 'custom-challenge@example.com') {
  await page.addInitScript(({ principal }) => {
    sessionStorage.setItem('poke.access-token', `token-for-${principal}`);
    sessionStorage.setItem('poke.account-principal', principal);
  }, { principal });
}

async function stubOfficialMy(page: Page) {
  await page.route('**/api/v1/user/challenges', route => route.fulfill({
    json: { items: [], total_count: 0 },
  }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({
    json: { items: [], total_count: 0 },
  }));
}

async function stubRecommendations(page: Page, items: unknown[] = [medicationA, medicationB, supplement]) {
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({
    json: { items, totalCount: items.length },
  }));
}

test('recommendations use server names and carry the selected template id', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page);

  await page.goto('/challenges/tailored');

  await expect(page.getByRole('heading', { name: '맞춤 챌린지', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: new RegExp(medicationA.challengeName) }))
    .toHaveAttribute('href', '/challenges/tailored/medication?templateId=31');
  await expect(page.getByRole('link', { name: new RegExp(medicationB.challengeName) }))
    .toHaveAttribute('href', '/challenges/tailored/medication?templateId=32');
  await expect(page.getByText('추천 챌린지')).toHaveCount(0);
  await expect(page.getByText('다음 진료 준비')).toHaveCount(0);
});

test('recommendations expose empty, forbidden, and retryable states without mock cards', async ({ page }) => {
  await authenticate(page);
  let forbidden = true;
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => {
    return forbidden
      ? route.fulfill({ status: 403, json: { code: 'FORBIDDEN', message: '맞춤 챌린지를 볼 권한이 없어요.' } })
      : route.fulfill({ json: { items: [], totalCount: 0 } });
  });

  await page.goto('/challenges/tailored');
  await expect(page.getByRole('alert')).toContainText('맞춤 챌린지를 볼 권한이 없어요.');
  forbidden = false;
  await page.getByRole('button', { name: '다시 불러오기' }).click();
  await expect(page.getByText('지금 참여할 수 있는 맞춤 챌린지가 없어요.')).toBeVisible();
  await expect(page.getByText('나만의 작은 루틴')).toHaveCount(0);
});

test('medication single selection retries its single POST with a stable key', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [medicationA]);
  const requests: Array<{ targetIds: number[]; idempotencyKey: string }> = [];
  await page.route('**/api/v1/user/custom-challenge-recommendations/*/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[]; idempotencyKey: string };
    requests.push(body);
    return requests.length === 1
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '잠시 연결이 끊겼어요.' } })
      : route.fulfill({ status: 201, json: participation({
        id: 702,
        actualEndDate: '2026-09-30',
        targets: [{ id: 902, sourceId: 102, name: '튼튼병원 2차 처방' }],
      }) });
  });
  await page.route('**/api/v1/user/custom-challenge-participations/702', route => route.fulfill({
    json: participation({
      id: 702,
      actualEndDate: '2026-09-30',
      targets: [{ id: 902, sourceId: 102, name: '튼튼병원 2차 처방' }],
    }),
  }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));

  await page.goto('/challenges/tailored/medication?templateId=31');
  const firstEpisode = page.getByLabel('서울의원 1차 처방 선택');
  const secondEpisode = page.getByLabel('튼튼병원 2차 처방 선택');
  await expect(page.getByText(/남은 복약 일정 전체가 목표 기간/)).toBeVisible();
  await expect(page.getByText(/7일/)).toHaveCount(0);
  await firstEpisode.check();
  await firstEpisode.uncheck();
  await secondEpisode.check();
  await expect(firstEpisode).not.toBeChecked();
  await expect(secondEpisode).toBeChecked();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();
  await expect(page.getByRole('alert')).toContainText('잠시 연결이 끊겼어요.');
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page).toHaveURL(/\/challenges\/custom-participations\/702$/);

  expect(requests.map(item => item.targetIds)).toEqual([[102], [102]]);
  expect(requests[1].idempotencyKey).toBe(requests[0].idempotencyKey);
});

test('medication multi selection creates separate participations and shows both in My', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [medicationA]);
  await stubOfficialMy(page);
  const requests: Array<{ targetIds: number[]; idempotencyKey: string }> = [];
  const joined: ReturnType<typeof participation>[] = [];
  await page.route('**/api/v1/user/custom-challenge-recommendations/31/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[]; idempotencyKey: string };
    requests.push(body);
    const item = participation({
      id: body.targetIds[0] === 101 ? 701 : 702,
      targets: [{ id: 800 + body.targetIds[0], sourceId: body.targetIds[0], name: body.targetIds[0] === 101 ? '서울의원 1차 처방' : '튼튼병원 2차 처방' }],
    });
    joined.push(item);
    return route.fulfill({ status: 201, json: item });
  });
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: joined, totalCount: joined.length },
  }));

  await page.goto('/challenges/tailored/medication?templateId=31');
  await page.getByLabel('서울의원 1차 처방 선택').check();
  await page.getByLabel('튼튼병원 2차 처방 선택').check();
  await expect(page.getByLabel('서울의원 1차 처방 선택')).toBeChecked();
  await expect(page.getByLabel('튼튼병원 2차 처방 선택')).toBeChecked();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();

  await expect(page).toHaveURL(/\/challenges$/);
  expect(requests.map(request => request.targetIds)).toEqual([[101], [102]]);
  expect(new Set(requests.map(request => request.idempotencyKey)).size).toBe(2);
  const section = page.getByRole('region', { name: '진행 중인 챌린지' });
  await expect(section.locator('a[href="/challenges/custom-participations/701"]')).toBeVisible();
  await expect(section.locator('a[href="/challenges/custom-participations/702"]')).toBeVisible();
});

test('medication partial failure preserves successes and retries only failed episodes', async ({ page }, testInfo) => {
  await authenticate(page);
  await stubRecommendations(page, [{ ...medicationA, targets: [
    ...medicationA.targets,
    { id: 103, name: '바른의원 3차 처방', existingParticipationId: null },
  ] }]);
  await stubOfficialMy(page);
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
  const requests: Array<{ targetIds: number[]; idempotencyKey: string }> = [];
  let failSecond = true;
  await page.route('**/api/v1/user/custom-challenge-recommendations/31/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[]; idempotencyKey: string };
    requests.push(body);
    if (body.targetIds[0] === 102 && failSecond) {
      return route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '잠시 연결이 끊겼어요.' } });
    }
    return route.fulfill({ status: 201, json: participation({ id: body.targetIds[0] + 600 }) });
  });

  await page.goto('/challenges/tailored/medication?templateId=31');
  const first = page.getByLabel('서울의원 1차 처방 선택');
  const second = page.getByLabel('튼튼병원 2차 처방 선택');
  const third = page.getByLabel('바른의원 3차 처방 선택');
  await first.check();
  await second.check();
  await third.check();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();

  await expect(page.getByRole('alert')).toContainText('튼튼병원 2차 처방');
  await expect(page.getByRole('alert')).toContainText('잠시 연결이 끊겼어요.');
  await expect(first).toBeDisabled();
  await expect(first).not.toBeChecked();
  await expect(third).toBeDisabled();
  await expect(second).toBeChecked();
  await expect(page.locator('a[href="/challenges/custom-participations/701"]')).toBeVisible();
  await expect(page.locator('a[href="/challenges/custom-participations/703"]')).toBeVisible();
  expect(requests.map(request => request.targetIds)).toEqual([[101], [102], [103]]);
  await page.screenshot({ path: testInfo.outputPath('partial-retry.png'), fullPage: true });

  failSecond = false;
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  expect(requests.map(request => request.targetIds)).toEqual([[101], [102], [103], [102]]);
  expect(requests[3].idempotencyKey).toBe(requests[1].idempotencyKey);
});

test('medication all failures keep separate keys when the user changes the retry selection', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [medicationA]);
  const requests: Array<{ targetIds: number[]; idempotencyKey: string }> = [];
  let failing = true;
  await page.route('**/api/v1/user/custom-challenge-recommendations/31/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[]; idempotencyKey: string };
    requests.push(body);
    return failing
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '잠시 후 다시 시도해주세요.' } })
      : route.fulfill({ status: 201, json: participation({ id: 702 }) });
  });
  await page.route('**/api/v1/user/custom-challenge-participations/702', route => route.fulfill({
    json: participation({ id: 702 }),
  }));
  await page.goto('/challenges/tailored/medication?templateId=31');
  const first = page.getByLabel('서울의원 1차 처방 선택');
  const second = page.getByLabel('튼튼병원 2차 처방 선택');
  await first.check();
  await second.check();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();
  await expect(page.getByRole('alert')).toContainText('서울의원 1차 처방');
  await expect(page.getByRole('alert')).toContainText('튼튼병원 2차 처방');
  await expect(first).toBeChecked();
  await expect(second).toBeChecked();
  expect(new Set(requests.map(request => request.idempotencyKey)).size).toBe(2);
  failing = false;
  await first.uncheck();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();
  await expect(page).toHaveURL(/\/challenges\/custom-participations\/702$/);
  expect(requests.map(request => request.targetIds)).toEqual([[101], [102], [102]]);
  expect(requests[2].idempotencyKey).toBe(requests[1].idempotencyKey);
});

test('medication excludes an already participating episode and locks the batch while pending', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [{ ...medicationA, targets: [
    ...medicationA.targets,
    { id: 103, name: '이미 참여한 처방', existingParticipationId: 799 },
  ] }]);
  await stubOfficialMy(page);
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
  const targetRequests: number[][] = [];
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/user/custom-challenge-recommendations/31/participations', async route => {
    const { targetIds } = route.request().postDataJSON() as { targetIds: number[] };
    targetRequests.push(targetIds);
    await gate;
    await route.fulfill({ status: 201, json: participation({ id: 600 + targetIds[0] }) });
  });
  await page.goto('/challenges/tailored/medication?templateId=31');
  await expect(page.getByRole('button', { name: '선택한 처방으로 참여하기' })).toBeDisabled();
  await expect(page.getByLabel('이미 참여한 처방 선택')).toBeDisabled();
  await page.getByLabel('서울의원 1차 처방 선택').check();
  await page.getByLabel('튼튼병원 2차 처방 선택').check();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();
  await expect(page.getByRole('button', { name: '참여 처리 중' })).toBeDisabled();
  await expect(page.getByLabel('서울의원 1차 처방 선택')).toBeDisabled();
  await expect(page.getByLabel('튼튼병원 2차 처방 선택')).toBeDisabled();
  release();
  await expect(page).toHaveURL(/\/challenges$/);
  expect(targetRequests).toEqual([[101], [102]]);
});

test('a medication 401 stops later sequential POSTs immediately', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [medicationA]);
  const targetRequests: number[][] = [];
  await page.route('**/api/v1/user/custom-challenge-recommendations/*/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[] };
    targetRequests.push(body.targetIds);
    return route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED', message: '로그인이 필요해요.' } });
  });

  await page.goto('/challenges/tailored/medication?templateId=31');
  await page.getByLabel('서울의원 1차 처방 선택').check();
  await page.getByLabel('튼튼병원 2차 처방 선택').check();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();

  await expect(page).toHaveURL(/\/login$/);
  expect(targetRequests).toEqual([[101]]);
});

test('supplement sends one canonical set and keeps its key when retrying', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [supplement]);
  const joinedParticipation = participation({
    id: 801,
    templateId: 41,
    challengeType: 'SUPPLEMENT',
    challengeName: supplement.challengeName,
    targets: [201, 203].map((sourceId, index) => ({ id: 810 + index, sourceId, name: `영양제 ${sourceId}` })),
  });
  const requests: Array<{ targetIds: number[]; idempotencyKey: string }> = [];
  await page.route('**/api/v1/user/custom-challenge-recommendations/41/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[]; idempotencyKey: string };
    requests.push(body);
    return requests.length === 1
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '다시 시도해주세요.' } })
      : route.fulfill({ status: 201, json: joinedParticipation });
  });
  await page.route('**/api/v1/user/custom-challenge-participations/801', route => route.fulfill({
    json: joinedParticipation,
  }));

  await page.goto('/challenges/tailored/supplement?templateId=41');
  await page.getByLabel('비타민D 선택').check();
  await page.getByLabel('오메가3 선택').check();
  await page.getByRole('button', { name: '선택한 영양제로 참여하기' }).click();
  await expect(page.getByRole('alert')).toContainText('다시 시도해주세요.');
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page).toHaveURL(/\/challenges\/custom-participations\/801$/);

  expect(requests).toHaveLength(2);
  expect(requests[0].targetIds).toEqual([201, 203]);
  expect(requests[1].targetIds).toEqual([201, 203]);
  expect(requests[1].idempotencyKey).toBe(requests[0].idempotencyKey);
});

test('My lists custom participation independently and detail renders only server-derived progress', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-09T09:00:00+09:00'));
  await authenticate(page);
  await stubOfficialMy(page);
  const item = participation();
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [item], totalCount: 1 },
  }));
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: item }));

  await page.goto('/challenges');
  const section = page.getByRole('region', { name: '진행 중인 챌린지' });
  await expect(section.getByText(item.challengeName)).toBeVisible();
  await expect(section.getByText('2 / 7일')).toBeVisible();
  await section.getByRole('link', { name: `${item.challengeName} 자세히 보기` }).click();

  await expect(page.getByRole('heading', { name: item.challengeName })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: '맞춤 챌린지 진행률' })).toHaveAttribute('aria-valuenow', '28.57');
  const selectedRecords = recordsForDate(page, '2026-09-09');
  await expect(selectedRecords.getByRole('listitem')).toHaveCount(2);
  await expect(selectedRecords.getByRole('listitem').first()).toContainText('아침');
  await expect(selectedRecords.getByRole('listitem').last()).toContainText('저녁');
  await expect(selectedRecords.getByRole('listitem').first()).toContainText('완료');
  await expect(page.getByText('2 / 2회 완료', { exact: true })).toBeVisible();
  const detail = page.locator('main');
  await expect(detail.getByRole('button', { name: /했어요|복약|인증/ })).toHaveCount(0);
  await expect(detail.getByText(/배지/)).toHaveCount(0);
});

test('custom detail back returns through My without reopening the detail', async ({ page }) => {
  await authenticate(page);
  await stubOfficialMy(page);
  const item = participation();
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [item], totalCount: 1 },
  }));
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: item }));

  await page.goto('/challenges');
  await page.getByRole('region', { name: '진행 중인 챌린지' })
    .getByRole('link', { name: `${item.challengeName} 자세히 보기` })
    .click();
  await expect(page).toHaveURL(/\/challenges\/custom-participations\/701$/);

  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(/\/challenges$/);
  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page).toHaveURL(/\/home$/);
});

test('route re-entry refetches custom progress and Home actions never POST a custom challenge', async ({ page }) => {
  await authenticate(page);
  await stubOfficialMy(page);
  let completedCount = 2;
  let customReads = 0;
  let customPosts = 0;
  await page.route('**/api/v1/user/custom-challenge-participations', route => {
    if (route.request().method() === 'POST') customPosts += 1;
    customReads += 1;
    const item = participation({ completedCount });
    return route.fulfill({ json: { items: [item], totalCount: 1 } });
  });
  await page.route('**/api/v1/display/med/nutr/rank', route => route.fulfill({ status: 204 }));
  await page.route('**/api/v1/med/user-suppl-nutr?*', route => route.fulfill({ json: {
    items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null,
  } }));
  await page.route('**/api/v1/medications', route => route.fulfill({ json: [] }));
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().includes('/custom-challenge')) customPosts += 1;
  });

  await page.goto('/challenges');
  await expect(page.getByRole('region', { name: '진행 중인 챌린지' }).getByText('1 / 7일')).toBeVisible();
  const firstEntryReads = customReads;
  await page.goto('/home');
  completedCount = 4;
  await page.goto('/challenges');
  await expect(page.getByRole('region', { name: '진행 중인 챌린지' }).getByText('2 / 7일')).toBeVisible();
  expect(customReads).toBeGreaterThan(firstEntryReads);
  expect(customPosts).toBe(0);
});

test('a delayed recommendation response cannot replace another account route', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: [], total_count: 0, offset: 0, limit: 100 },
  }));
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/user/custom-challenge-recommendations', async route => {
    await gate;
    await route.fulfill({ json: { items: [medicationA], totalCount: 1 } });
  });

  await page.goto('/challenges/tailored');
  await page.evaluate(() => {
    sessionStorage.setItem('poke.account-principal', 'another-account@example.com');
    window.history.pushState({}, '', '/challenges/browse');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  release();

  await expect(page).toHaveURL(/\/challenges\/browse$/);
  await expect(page.getByRole('heading', { name: '공식 챌린지' })).toBeVisible();
  await expect(page.getByText(medicationA.challengeName)).toHaveCount(0);
});

test('a delayed join cannot navigate after leaving the target page', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [medicationA]);
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: [], total_count: 0, offset: 0, limit: 100 },
  }));
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const targetRequests: number[][] = [];
  await page.route('**/api/v1/user/custom-challenge-recommendations/31/participations', async route => {
    targetRequests.push(route.request().postDataJSON().targetIds);
    await gate;
    await route.fulfill({ status: 201, json: participation() });
  });

  await page.goto('/challenges/tailored/medication?templateId=31');
  await page.getByLabel('서울의원 1차 처방 선택').check();
  await page.getByLabel('튼튼병원 2차 처방 선택').check();
  await page.getByRole('button', { name: '선택한 처방으로 참여하기' }).click();
  await page.evaluate(() => {
    window.history.pushState({}, '', '/challenges/browse');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/challenges\/browse$/);
  release();
  await page.waitForTimeout(100);

  await expect(page).toHaveURL(/\/challenges\/browse$/);
  await expect(page.getByRole('heading', { name: '공식 챌린지' })).toBeVisible();
  expect(targetRequests).toEqual([[101]]);
});

test('custom list failure stays inside its section while official My remains usable', async ({ page }) => {
  await authenticate(page);
  await stubOfficialMy(page);
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    status: 503,
    json: { code: 'TEMPORARY', message: '맞춤 진행률을 불러오지 못했어요.' },
  }));

  await page.goto('/challenges');

  await expect(page.getByRole('heading', { name: '진행 중인 챌린지' })).toBeVisible();
  const custom = page.getByRole('region', { name: '진행 중인 챌린지' });
  await expect(custom.getByRole('alert')).toContainText('맞춤 진행률을 불러오지 못했어요.');
  await expect(page.getByRole('link', { name: '공식 챌린지 둘러보기' })).toBeVisible();
});

test('custom My remains available when the official dashboard fails', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/user/challenges', route => route.fulfill({
    status: 503,
    json: { code: 'TEMPORARY', message: '공식 챌린지를 불러오지 못했어요.' },
  }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [participation()], totalCount: 1 },
  }));

  await page.goto('/challenges');

  await expect(page.getByRole('alert')).toContainText('공식 챌린지를 불러오지 못했어요.');
  await expect(page.getByRole('region', { name: '진행 중인 챌린지' }).getByText(medicationA.challengeName)).toBeVisible();
});

test('custom My can finish loading while the official dashboard is still pending', async ({ page }) => {
  await authenticate(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/user/challenges', async route => {
    await gate;
    await route.fulfill({ json: { items: [], total_count: 0 } });
  });
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [participation()], totalCount: 1 },
  }));

  await page.goto('/challenges');
  await expect(page.getByRole('region', { name: '진행 중인 챌린지' }).getByText(medicationA.challengeName)).toBeVisible();
  await expect(page.getByRole('status', { name: '내 챌린지 불러오는 중' })).toBeVisible();
  release();
});

test('official My and browse keep their page heading outside the padded main', async ({ page }) => {
  await authenticate(page);
  await stubOfficialMy(page);
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [], totalCount: 0 },
  }));
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({
    json: { items: [], total_count: 0, offset: 0, limit: 100 },
  }));

  for (const path of ['/challenges', '/challenges/browse']) {
    await page.goto(path);
    const back = page.getByRole('button', { name: '뒤로 가기' });
    await expect(back).toBeVisible();
    await expect(page.locator('main').getByRole('button', { name: '뒤로 가기' })).toHaveCount(0);
  }
});

test('custom screens keep their shared header outside the padded main', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [medicationA]);
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({
    json: participation(),
  }));

  for (const path of [
    '/challenges/tailored',
    '/challenges/tailored/medication?templateId=31',
    '/challenges/custom-participations/701',
  ]) {
    await page.goto(path);
    const back = page.getByRole('button', { name: '뒤로 가기' });
    await expect(back).toBeVisible();
    await expect(page.locator('main').getByRole('button', { name: '뒤로 가기' })).toHaveCount(0);
  }
});

test('custom detail calendar shows only the selected date records', async ({ page }) => {
  await page.clock.setFixedTime('2026-09-10T03:00:00Z');
  await authenticate(page);
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({
    json: participation({
      targetCount: 2,
      completedCount: 1,
      progressRate: '50.00',
      occurrences: [
        { id: 901, targetId: 801, scheduledDate: '2026-09-09', slot: 'MORNING', scheduledAt: '2026-09-09T08:00:00+09:00', isCompleted: true },
        { id: 902, targetId: 801, scheduledDate: '2026-09-10', slot: 'EVENING', scheduledAt: '2026-09-10T19:00:00+09:00', isCompleted: false },
      ],
    }),
  }));

  await page.goto('/challenges/custom-participations/701');

  const records = recordsForDate(page, '2026-09-10');
  await expect(records).toContainText('저녁');
  await expect(records).not.toContainText('아침');
  await page.getByRole('button', { name: '2026.09.09, 모두 완료' }).click();
  await expect(recordsForDate(page, '2026-09-09')).toContainText('아침');
  await expect(records).toHaveCount(0);
});

test('zero remaining goals render without an invented last goal date', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({
    json: participation({
      actualEndDate: null,
      targetCount: 0,
      completedCount: 0,
      progressRate: '0.00',
      occurrences: [],
    }),
  }));

  await page.goto('/challenges/custom-participations/701');

  await expect(page.getByRole('heading', { name: '내 진행률' })).toBeVisible();
  await expect(page.getByText('예정된 목표 없음', { exact: true })).toBeVisible();
  await expect(page.getByText('0 / 0일', { exact: true })).toBeVisible();
  await expect(page.getByText('진행 중', { exact: true })).toBeVisible();
  await expect(page.getByText('이날은 목표 기록이 없어요.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '다음 날짜' })).toHaveCount(0);
});

test('completed medication detail keeps the server final snapshot and its awarded badge', async ({ page }) => {
  await authenticate(page);
  const frozen = participation({
      status: 'COMPLETED',
      joinedAt: '2026-09-09T09:00:00+09:00',
      endAt: '2026-09-30T23:59:59+09:00',
      actualEndDate: '2026-09-30',
      targetCount: 42,
      completedCount: 42,
      progressRate: '100.00',
      targetDayCount: 21,
      completedDayCount: 21,
      dayProgressRate: '100.00',
      occurrences: [],
    });
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: frozen }));
  await page.route('**/api/v1/user/custom-challenge-participations/701/claim-reward', route => route.fulfill({
    json: {
      participation: frozen,
      award: {
        id: 501,
        participationId: 701,
        badgeId: 9,
        badgeName: '복약 루틴 배지',
        badgeImagePath: '/media/badges/medication-routine.png',
        awardedAt: '2026-09-30T23:59:59+09:00',
      },
      newlyAwarded: false,
    },
  }));

  await page.goto('/challenges/custom-participations/701');

  await expect(page.getByText('최종 결과', { exact: true })).toBeVisible();
  await expect(page.getByText('21 / 21일', { exact: true })).toBeVisible();
  await expect(page.getByText('2026.09.09 ~ 2026.09.30', { exact: true })).toBeVisible();
  await expect(page.getByRole('img', { name: '복약 루틴 배지' })).toBeVisible();
  await expect(page.getByText('2026.09.30 획득', { exact: true })).toBeVisible();
  await expect(page.getByText(/7일/)).toHaveCount(0);
});

test('My badges shows official and custom awards with the same numeric badge id independently', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: {
    items: [{
      id: 71,
      name: '공식 걷기',
      phrase: '걷기',
      description: null,
      challenge_type_code: 'OFFICIAL',
      period_code: 'DAILY',
      duration_days: 7,
      check_type_code: 'SELF',
      frequency_code: 'DAILY',
      recruit_start_at: '2026-09-01T00:00:00+09:00',
      recruit_end_at: '2026-09-30T23:59:59+09:00',
      reward_badge: { id: 9, name: '공식 걷기 배지', description: null, image_path: '/media/badges/walk.png' },
      can_join: true,
      participation_id: null,
    }],
    total_count: 1,
    offset: 0,
    limit: 100,
  } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: {
    items: [{
      id: 301,
      user_id: 1,
      badge_id: 9,
      challenge_id: 71,
      user_challenge_id: 81,
      status: 'AWARDED',
      badge_name: '공식 걷기 배지',
      badge_image_path: '/media/badges/walk.png',
      awarded_at: '2026-09-08T12:00:00+09:00',
      revoked_at: null,
      revoke_reason: null,
    }],
    total_count: 1,
  } }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: {
    items: [{
      id: 501,
      participationId: 701,
      badgeId: 9,
      badgeName: '복약 루틴 배지',
      badgeImagePath: '/media/badges/medication-routine.png',
      awardedAt: '2026-09-30T23:59:59+09:00',
    }],
    totalCount: 1,
  } }));

  await page.goto('/challenges/badges');

  await expect(page.getByText('모은 배지 2종 · 총 2회 획득')).toBeVisible();
  await expect(page.getByRole('link', { name: '공식 걷기 배지, 1회 획득' })).toHaveAttribute('href', '/challenges/badges/9');
  await expect(page.getByRole('link', { name: '복약 루틴 배지, 1회 획득' })).toHaveAttribute('href', '/challenges/custom-participations/701');
});

test('custom badge failure is retryable without hiding official badges', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: {
    items: [], total_count: 0, offset: 0, limit: 100,
  } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: {
    items: [{
      id: 301,
      user_id: 1,
      badge_id: 9,
      challenge_id: 71,
      user_challenge_id: 81,
      status: 'AWARDED',
      badge_name: '공식 걷기 배지',
      badge_image_path: '/media/badges/walk.png',
      awarded_at: '2026-09-08T12:00:00+09:00',
      revoked_at: null,
      revoke_reason: null,
    }],
    total_count: 1,
  } }));
  let customFails = true;
  await page.route('**/api/v1/user/custom-challenges/badges', route => customFails
    ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '맞춤 배지를 불러오지 못했어요.' } })
    : route.fulfill({ json: { items: [], totalCount: 0 } }));

  await page.goto('/challenges/badges');

  await expect(page.getByRole('link', { name: '공식 걷기 배지, 1회 획득' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('맞춤 배지를 불러오지 못했어요.');
  customFails = false;
  await page.getByRole('button', { name: '맞춤 배지 다시 불러오기' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('link', { name: '공식 걷기 배지, 1회 획득' })).toBeVisible();
});

test('official badge failure is retryable without hiding custom badges', async ({ page }) => {
  await authenticate(page);
  let officialFails = true;
  await page.route('**/api/v1/user/challenge-catalog?*', route => officialFails
    ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '공식 배지를 불러오지 못했어요.' } })
    : route.fulfill({ json: { items: [], total_count: 0, offset: 0, limit: 100 } }));
  await page.route('**/api/v1/user/badges', route => route.fulfill({ json: {
    items: [], total_count: 0,
  } }));
  await page.route('**/api/v1/user/custom-challenges/badges', route => route.fulfill({ json: {
    items: [{
      id: 501,
      participationId: 701,
      badgeId: 9,
      badgeName: '복약 루틴 배지',
      badgeImagePath: '/media/badges/medication-routine.png',
      awardedAt: '2026-09-30T23:59:59+09:00',
    }],
    totalCount: 1,
  } }));

  await page.goto('/challenges/badges');

  await expect(page.getByRole('link', { name: '복약 루틴 배지, 1회 획득' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('공식 배지를 불러오지 못했어요.');
  officialFails = false;
  await page.getByRole('button', { name: '공식 배지 다시 불러오기' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('link', { name: '복약 루틴 배지, 1회 획득' })).toBeVisible();
});

test.describe('Asia/Seoul occurrence boundary', () => {
  test.use({ timezoneId: 'America/Los_Angeles' });

  test('uses the backend Seoul date even when the browser local date is a day behind', async ({ page }) => {
    await page.clock.setFixedTime('2026-09-09T15:30:00.000Z');
    await authenticate(page);
    await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({
      json: participation({
        targetCount: 2,
        completedCount: 1,
        progressRate: '50.00',
        occurrences: [
          { id: 901, targetId: 801, scheduledDate: '2026-09-09', slot: 'MORNING', scheduledAt: '2026-09-09T08:00:00+09:00', isCompleted: true },
          { id: 902, targetId: 801, scheduledDate: '2026-09-10', slot: 'MORNING', scheduledAt: '2026-09-10T08:00:00+09:00', isCompleted: false },
        ],
      }),
    }));

    await page.goto('/challenges/custom-participations/701');
    await expect(recordsForDate(page, '2026-09-10')).toContainText('아침');
    await expect(page.getByRole('button', { name: '2026.09.10, 0/1 완료, 오늘' })).toHaveAttribute('aria-pressed', 'true');
    await expect(recordsForDate(page, '2026-09-09')).toHaveCount(0);
  });
});

for (const kind of ['MEDICATION', 'SUPPLEMENT']) {
  test(`${kind} calendar groups completion and browses future records without writes`, async ({ page }, testInfo) => {
    await page.clock.setFixedTime('2026-09-10T03:00:00Z');
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate(page);
    const writes: string[] = [];
    page.on('request', request => {
      if (request.url().includes('/api/v1/') && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) writes.push(`${request.method()} ${request.url()}`);
    });
    await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: participation({
      challengeType: kind,
      challengeName: kind === 'SUPPLEMENT' ? '영양제 루틴 이어가기' : '처방 일정 지키기',
      targetCount: 4, completedCount: 1, progressRate: '25.00',
      actualEndDate: '2026-10-02',
      targets: [
        { id: 801, sourceId: 101, name: kind === 'SUPPLEMENT' ? '오메가3' : '서울의원 처방' },
        ...(kind === 'SUPPLEMENT' ? [{ id: 802, sourceId: 102, name: '유산균' }] : []),
      ],
      occurrences: [
        { id: 904, targetId: 801, scheduledDate: '2026-10-02', slot: 'EVENING', scheduledAt: '2026-10-02T19:00:00+09:00', isCompleted: false },
        { id: 903, targetId: 801, scheduledDate: '2026-09-11', slot: 'MORNING', scheduledAt: '2026-09-11T08:00:00+09:00', isCompleted: false },
        { id: 902, targetId: kind === 'SUPPLEMENT' ? 802 : 801, scheduledDate: '2026-09-10', slot: 'EVENING', scheduledAt: '2026-09-10T19:00:00+09:00', isCompleted: false },
        { id: 901, targetId: 801, scheduledDate: '2026-09-10', slot: 'MORNING', scheduledAt: '2026-09-10T08:00:00+09:00', isCompleted: true },
      ],
    }) }));
    await page.goto('/challenges/custom-participations/701');
    await expect(page.getByRole('button', { name: '2026.09.10, 1/2 완료, 오늘' })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: /2026.09.08/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '2026.09.12, 목표 없음' })).toBeEnabled();
    const records = recordsForDate(page, '2026-09-10');
    await expect(records.getByRole('listitem')).toHaveCount(2);
    await expect(records.getByRole('listitem').first()).toContainText('아침');
    if (kind === 'SUPPLEMENT') {
      await expect(records).toContainText('오메가3');
      await expect(records).toContainText('유산균');
    }
    await page.getByRole('region', { name: '챌린지 달력', exact: true }).screenshot({ path: testInfo.outputPath('calendar.png') });
    await page.getByRole('button', { name: '2026.09.11, 예정 1회' }).click();
    await expect(recordsForDate(page, '2026-09-11')).toContainText('예정');
    await page.getByRole('button', { name: '2026.10.02, 예정 1회' }).click();
    await expect(recordsForDate(page, '2026-10-02')).toContainText('저녁');
    await page.getByRole('button', { pressed: true }).press('ArrowRight');
    await expect(page.getByRole('button', { name: '2026.10.02, 예정 1회' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { pressed: true }).press('Home');
    await expect(page.getByRole('button', { name: '2026.09.09, 목표 없음' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { pressed: true }).press('ArrowLeft');
    await expect(page.getByRole('button', { name: '2026.09.09, 목표 없음' })).toHaveAttribute('aria-pressed', 'true');
    expect(writes).toEqual([]);
  });
}

test('ended calendar starts today and browses final goal records across a year boundary', async ({ page }) => {
  await page.clock.setFixedTime('2027-02-10T03:00:00Z');
  await authenticate(page);
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: participation({
    status: 'EXPIRED', joinedAt: '2026-12-31T09:00:00+09:00', actualEndDate: '2027-01-01',
    occurrences: [
      { id: 901, targetId: 801, scheduledDate: '2026-12-31', slot: 'LUNCH', scheduledAt: '2026-12-31T12:00:00+09:00', isCompleted: true },
      { id: 902, targetId: 801, scheduledDate: '2027-01-01', slot: 'MORNING', scheduledAt: '2027-01-01T08:00:00+09:00', isCompleted: false },
    ],
  }) }));
  await page.goto('/challenges/custom-participations/701');
  await expect(recordsForDate(page, '2027-02-10')).toContainText('이날은 목표 기록이 없어요.');
  await page.getByRole('button', { name: /^2027.01.01,/ }).click();
  await expect(recordsForDate(page, '2027-01-01')).toContainText('미완료');
  await expect(page.getByRole('heading', { name: '최종 결과' })).toBeVisible();
  await page.getByRole('button', { name: '2026.12.31, 모두 완료' }).click();
  await expect(recordsForDate(page, '2026-12-31')).toContainText('점심');
});

test('calendar uses Seoul join date for UTC instants at the month boundary', async ({ page }) => {
  await page.clock.setFixedTime('2026-10-01T01:00:00Z');
  await authenticate(page);
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: participation({
    joinedAt: '2026-09-30T15:30:00Z', actualEndDate: '2026-10-02',
    occurrences: [{ id: 901, targetId: 801, scheduledDate: '2026-10-02', slot: 'MORNING', scheduledAt: '2026-10-02T08:00:00+09:00', isCompleted: false }],
  }) }));
  await page.goto('/challenges/custom-participations/701');
  await expect(page.getByRole('button', { name: '2026.10.01, 목표 없음, 오늘' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { pressed: true }).press('ArrowLeft');
  await expect(page.getByRole('button', { name: '2026.10.01, 목표 없음, 오늘' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('2026.10.01 ~ 2026.10.02', { exact: true })).toBeVisible();
  await expect(recordsForDate(page, '2026-10-01')).toContainText('이날은 목표 기록이 없어요.');
});

test('custom medication join uses badge and guide cards while retaining existing participation links', async ({ page }, testInfo) => {
  await authenticate(page);
  await stubRecommendations(page, [{ ...medicationA, targets: [
    { id: 101, name: '서울의원 1차 처방', existingParticipationId: 701 },
    { id: 102, name: '튼튼병원 2차 처방', existingParticipationId: 702 },
  ] }]);
  await page.route('**/media/badges/medication-routine.png', route => route.fulfill({
    contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><circle cx="32" cy="32" r="30" fill="#087d7d"/></svg>',
  }));
  await page.goto('/challenges/tailored/medication?templateId=31');
  const highlight = page.getByRole('region', { name: '복약 루틴 배지', exact: true });
  await expect(highlight.getByRole('img', { name: '복약 루틴 배지' })).toBeVisible();
  await expect(highlight).toContainText('처방 일정 달성 배지');
  await expect(page.getByRole('region', { name: '참여 안내', exact: true })).toContainText('처방 종료일까지');
  await page.getByRole('region', { name: '배지와 인증 안내' }).locator('summary').click();
  await expect(page.getByRole('region', { name: '배지와 인증 안내' })).toContainText('자동');
  await expect(page.getByLabel('서울의원 1차 처방 선택')).toBeDisabled();
  await expect(page.getByRole('link', { name: '이미 참여 중인 처방 보기' }).first()).toHaveAttribute('href', '/challenges/custom-participations/701');
  await expect(page.getByRole('button', { name: '선택한 처방으로 참여하기' })).toBeDisabled();
  await highlight.screenshot({ path: testInfo.outputPath('join-highlight.png') });
});

test('custom supplement join guides keep seven-day policy without inventing a missing badge', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [supplement]);
  await page.goto('/challenges/tailored/supplement?templateId=41');
  await expect(page.getByRole('region', { name: '참여 안내', exact: true })).toContainText('참여일 포함 7일');
  await page.getByRole('region', { name: '배지와 인증 안내' }).locator('summary').click();
  await expect(page.getByRole('region', { name: '배지와 인증 안내' })).toContainText('등록된 배지가 없어요');
  await page.getByLabel('오메가3 선택').check();
  await page.getByLabel('유산균 선택').check();
  await expect(page.getByRole('button', { name: '선택한 영양제로 참여하기' })).toBeEnabled();
});

for (const challengeType of ['MEDICATION', 'SUPPLEMENT']) {
  test(`${challengeType} cancel requires confirmation and preserves the cancelled entry in history`, async ({ page }) => {
    await authenticate(page);
    await stubOfficialMy(page);
    let current = participation({ challengeType });
    let calls = 0;
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: current }));
    await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [current], totalCount: 1 } }));
    await page.route('**/api/v1/user/custom-challenge-participations/701/cancel', async route => {
      expect(route.request().method()).toBe('POST');
      expect(route.request().postData()).toBeNull();
      calls += 1;
      await gate;
      current = participation({ challengeType, status: 'CANCELLED' });
      await route.fulfill({ json: current });
    });
    await page.goto('/challenges/custom-participations/701');
    await page.getByRole('button', { name: '챌린지 참여 취소', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('기존 복용 기록은 삭제되지 않아요');
    expect(calls).toBe(0);
    await dialog.getByRole('button', { name: '돌아가기', exact: true }).click();
    expect(calls).toBe(0);
    await page.getByRole('button', { name: '챌린지 참여 취소', exact: true }).click();
    await dialog.getByRole('button', { name: '참여 취소', exact: true }).click();
    await expect(dialog.getByRole('button', { name: '취소 중...' })).toBeDisabled();
    await dialog.getByRole('button', { name: '취소 중...' }).evaluate((button: HTMLButtonElement) => button.click());
    expect(calls).toBe(1);
    release();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByText('취소', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '챌린지 참여 취소', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: '내 챌린지로 돌아가기' }).click();
    await expect(page.getByRole('region', { name: '진행 중인 챌린지' }).getByRole('article')).toHaveCount(0);
    await page.getByRole('button', { name: '지난 기록 펼치기' }).click();
    await expect(page.getByRole('region', { name: '지난 기록' }).getByRole('article')).toContainText('취소');
    expect(calls).toBe(1);
  });
}

test('custom cancellation errors stay retryable and ended state is reconciled on conflict', async ({ page }) => {
  await authenticate(page);
  let expired = false;
  let calls = 0;
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: participation({ status: expired ? 'EXPIRED' : 'ACTIVE' }) }));
  await page.route('**/api/v1/user/custom-challenge-participations/701/cancel', route => {
    calls += 1;
    if (calls === 1) return route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '잠시 후 다시 시도해주세요.' } });
    expired = true;
    return route.fulfill({ status: 409, json: { code: 'CUSTOM_CHALLENGE_CANCEL_NOT_ALLOWED', message: '진행 중인 챌린지만 취소할 수 있어요.' } });
  });
  await page.goto('/challenges/custom-participations/701');
  await page.getByRole('button', { name: '챌린지 참여 취소', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: '참여 취소', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('잠시 후 다시');
  await dialog.getByRole('button', { name: '참여 취소', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('진행 중인 챌린지만');
  await expect(dialog.getByRole('button', { name: '참여 취소', exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: '돌아가기', exact: true }).click();
  await expect(page.getByText('종료', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '챌린지 참여 취소', exact: true })).toHaveCount(0);
});

test('Home shows every active custom participation without a two-item cap', async ({ page }) => {
  await authenticate(page);
  await page.route(url => url.pathname.startsWith('/api/v1/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/medications', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({ json: { items: [
    participation(), participation({ id: 702, challengeName: '둘째 복약' }), participation({ id: 703, challengeName: '영양제 루틴', challengeType: 'SUPPLEMENT' }), participation({ id: 704, status: 'CANCELLED', challengeName: '취소한 복약' }),
  ], totalCount: 4 } }));
  await page.goto('/home');
  const summary = page.getByRole('region', { name: '맞춤 챌린지', exact: true });
  await expect(summary.getByRole('link', { name: /상세 보기$/ })).toHaveCount(3);
  await expect(summary.getByRole('link', { name: /영양제 루틴.*상세 보기/ })).toHaveAttribute('href', '/challenges/custom-participations/703');
  await expect(summary.getByText('취소한 복약')).toHaveCount(0);
});
