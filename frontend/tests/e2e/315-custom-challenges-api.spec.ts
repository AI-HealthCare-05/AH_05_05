import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(120_000);
test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(5_000);
  page.setDefaultNavigationTimeout(30_000);
});

const medicationA = {
  templateId: 31,
  challengeType: 'MEDICATION',
  challengeName: '처방 일정 지키기',
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
  action: 'NONE',
  targets: [
    { id: 203, name: '비타민D', existingParticipationId: 880 },
    { id: 201, name: '오메가3', existingParticipationId: null },
    { id: 202, name: '유산균', existingParticipationId: null },
  ],
};

function participation(overrides: Record<string, unknown> = {}) {
  return {
    id: 701,
    templateId: 31,
    challengeType: 'MEDICATION',
    challengeName: medicationA.challengeName,
    status: 'ACTIVE',
    joinedAt: '2026-09-09T09:00:00+09:00',
    endAt: '2026-09-16T09:00:00+09:00',
    actualEndDate: '2026-09-16',
    targetCount: 14,
    completedCount: 5,
    progressRate: '35.71',
    action: 'NONE',
    targets: [{ id: 801, sourceId: 101, name: '서울의원 1차 처방' }],
    occurrences: [{
      id: 901,
      targetId: 801,
      scheduledDate: '2026-09-09',
      slot: 'MORNING',
      scheduledAt: '2026-09-09T08:00:00+09:00',
      isCompleted: true,
    }],
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

test('medication joins one target per POST and retries only failures with stable keys', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [medicationA]);
  const requests: Array<{ templateId: string; targetIds: number[]; idempotencyKey: string }> = [];
  let failedOnce = false;
  await page.route('**/api/v1/user/custom-challenge-recommendations/*/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[]; idempotencyKey: string };
    requests.push({ templateId: new URL(route.request().url()).pathname.split('/').at(-2)!, ...body });
    if (body.targetIds[0] === 102 && !failedOnce) {
      failedOnce = true;
      return route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '잠시 연결이 끊겼어요.' } });
    }
    return route.fulfill({
      status: 201,
      json: participation({
        id: body.targetIds[0] === 101 ? 701 : 702,
        targets: [{ id: 800 + body.targetIds[0], sourceId: body.targetIds[0], name: body.targetIds[0] === 101 ? '서울의원 1차 처방' : '튼튼병원 2차 처방' }],
      }),
    });
  });

  await page.goto('/challenges/tailored/medication?templateId=31');
  await page.getByLabel('서울의원 1차 처방 선택').check();
  await page.getByLabel('튼튼병원 2차 처방 선택').check();
  await page.getByRole('button', { name: '선택한 대상으로 참여하기' }).click();
  await expect(page.getByRole('alert')).toContainText('잠시 연결이 끊겼어요.');
  await expect(page.getByText('서울의원 1차 처방 참여 완료')).toBeVisible();
  await page.getByRole('button', { name: '실패한 대상 다시 시도' }).click();
  await expect(page).toHaveURL(/\/challenges$/);

  expect(requests.map(item => item.targetIds)).toEqual([[101], [102], [102]]);
  expect(requests.map(item => item.templateId)).toEqual(['31', '31', '31']);
  expect(requests[0].idempotencyKey).not.toBe(requests[1].idempotencyKey);
  expect(requests[2].idempotencyKey).toBe(requests[1].idempotencyKey);
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
  await page.getByRole('button', { name: '선택한 대상으로 참여하기' }).click();

  await expect(page).toHaveURL(/\/login$/);
  expect(targetRequests).toEqual([[101]]);
});

test('supplement sends one canonical set and keeps its key when retrying', async ({ page }) => {
  await authenticate(page);
  await stubRecommendations(page, [supplement]);
  const requests: Array<{ targetIds: number[]; idempotencyKey: string }> = [];
  await page.route('**/api/v1/user/custom-challenge-recommendations/41/participations', route => {
    const body = route.request().postDataJSON() as { targetIds: number[]; idempotencyKey: string };
    requests.push(body);
    return requests.length === 1
      ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '다시 시도해주세요.' } })
      : route.fulfill({ status: 201, json: participation({
        id: 801,
        templateId: 41,
        challengeType: 'SUPPLEMENT',
        challengeName: supplement.challengeName,
        targets: body.targetIds.map((sourceId, index) => ({ id: 810 + index, sourceId, name: `영양제 ${sourceId}` })),
      }) });
  });

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
  await authenticate(page);
  await stubOfficialMy(page);
  const item = participation();
  await page.route('**/api/v1/user/custom-challenge-participations', route => route.fulfill({
    json: { items: [item], totalCount: 1 },
  }));
  await page.route('**/api/v1/user/custom-challenge-participations/701', route => route.fulfill({ json: item }));

  await page.goto('/challenges');
  const section = page.getByRole('region', { name: '맞춤 챌린지' });
  await expect(section.getByText(item.challengeName)).toBeVisible();
  await expect(section.getByText('5 / 14회')).toBeVisible();
  await section.getByRole('link', { name: `${item.challengeName} 자세히 보기` }).click();

  await expect(page.getByRole('heading', { name: item.challengeName })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: '맞춤 챌린지 진행률' })).toHaveAttribute('aria-valuenow', '35.71');
  await expect(page.getByText('2026.09.09 · 아침 · 완료')).toBeVisible();
  const detail = page.locator('main');
  await expect(detail.getByRole('button', { name: /했어요|복약|인증/ })).toHaveCount(0);
  await expect(detail.getByText(/배지/)).toHaveCount(0);
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
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().includes('/custom-challenge')) customPosts += 1;
  });

  await page.goto('/challenges');
  await expect(page.getByRole('region', { name: '맞춤 챌린지' }).getByText('2 / 14회')).toBeVisible();
  const firstEntryReads = customReads;
  await page.goto('/home');
  completedCount = 3;
  await page.goto('/challenges');
  await expect(page.getByRole('region', { name: '맞춤 챌린지' }).getByText('3 / 14회')).toBeVisible();
  expect(customReads).toBeGreaterThan(firstEntryReads);
  expect(customPosts).toBe(0);
});

test('a delayed recommendation response cannot replace another account route', async ({ page }) => {
  await authenticate(page);
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
  await page.route('**/api/v1/user/custom-challenge-recommendations/31/participations', async route => {
    await gate;
    await route.fulfill({ status: 201, json: participation() });
  });

  await page.goto('/challenges/tailored/medication?templateId=31');
  await page.getByLabel('서울의원 1차 처방 선택').check();
  await page.getByRole('button', { name: '선택한 대상으로 참여하기' }).click();
  await page.evaluate(() => {
    window.history.pushState({}, '', '/challenges/browse');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/challenges\/browse$/);
  release();
  await page.waitForTimeout(100);

  await expect(page).toHaveURL(/\/challenges\/browse$/);
  await expect(page.getByRole('heading', { name: '공식 챌린지' })).toBeVisible();
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
  const custom = page.getByRole('region', { name: '맞춤 챌린지' });
  await expect(custom.getByRole('alert')).toContainText('맞춤 진행률을 불러오지 못했어요.');
  await expect(page.getByRole('link', { name: '공식 챌린지 둘러보기' })).toBeVisible();
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
