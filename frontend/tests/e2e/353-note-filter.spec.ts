import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const NOTE_41 = {
  id: 901,
  careEpisodeId: 41,
  careEpisodeAlias: '감기약',
  careEpisodeStartDate: '2026-09-01',
  careEpisodeStatus: 'ACTIVE',
  availableMedications: [],
  medicationId: null,
  medication: null,
  dosedAt: '2026-09-02T08:00:00',
  body: '41번 처방 메모',
  createdAt: '2026-09-02T08:10:00',
  updatedAt: null,
};

const NOTE_42 = {
  ...NOTE_41,
  id: 902,
  careEpisodeId: 42,
  body: '42번 처방 메모',
};

const EPISODES = [
  { careEpisodeId: 42, alias: '감기약', startDate: '2026-09-01', status: 'ACTIVE', representativeMedicationName: '타이레놀', medicationCount: 3, noteCount: 1 },
  { careEpisodeId: 41, alias: '감기약', startDate: '2026-09-01', status: 'ACTIVE', representativeMedicationName: '아목시실린', medicationCount: 1, noteCount: 21 },
  { careEpisodeId: 43, alias: '감기약', startDate: '2025-12-31', status: 'COMPLETED', noteCount: 1 },
  { careEpisodeId: 44, alias: null, startDate: '2024-01-02', status: 'CANCELLED', noteCount: 1 },
  { careEpisodeId: 45, alias: '오래된 처방', startDate: null, status: 'COMPLETED', noteCount: 1 },
];

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function authenticate(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-filter-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-filter@example.com');
  });
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await authenticate(page);
});

test('요약 API의 모든 메모 처방을 아코디언에 보이고 처방 변경 시 목록 커서를 초기화한다', async ({ page }) => {
  const listQueries: string[] = [];
  await page.route('**/api/v1/med/notes/episodes**', (route) => fulfillJson(route, EPISODES));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    listQueries.push(url.searchParams.toString());
    if (url.searchParams.get('episodeId') === '42') {
      return fulfillJson(route, { items: [NOTE_42], total: 1, nextCursor: null });
    }
    if (url.searchParams.get('cursor') === 'page-2') {
      return fulfillJson(route, { items: [NOTE_42], total: 21, nextCursor: null });
    }
    return fulfillJson(route, { items: [NOTE_41], total: 21, nextCursor: 'page-2' });
  });

  await page.goto('/medications/notes');
  await page.getByRole('tab', { name: '메모 있는 처방' }).click();
  await expect(page.getByRole('button', { name: /감기약 · 2026년 9월 1일 · 타이레놀 외 2개 펼치기/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /감기약 · 2026년 9월 1일 · 아목시실린 펼치기/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /2024년 1월 2일 처방 .*펼치기/ })).toBeVisible();
  await page.getByRole('button', { name: /아목시실린 펼치기/ }).click();
  await page.getByRole('button', { name: '더 보기' }).click();
  await expect.poll(() => listQueries.some((query) => query.includes('episodeId=41') && query.includes('cursor=page-2'))).toBe(true);
  await page.getByRole('button', { name: /타이레놀 외 2개 펼치기/ }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=42');
  await expect(page.getByRole('heading', { name: '건강상태 기록 1개' })).toBeVisible();
  expect(listQueries.at(-1)).toBe('episodeId=42');
});

test('직접 접근한 episodeId를 열린 아코디언과 서버 목록 요청에 유지한다', async ({ page }) => {
  let requestedEpisodeId: string | null = null;
  await page.route('**/api/v1/med/notes/episodes**', (route) => fulfillJson(route, EPISODES));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    requestedEpisodeId = new URL(route.request().url()).searchParams.get('episodeId');
    return fulfillJson(route, { items: [NOTE_42], total: 1, nextCursor: null });
  });

  await page.goto('/medications/notes?episodeId=42');

  await expect(page.getByRole('button', { name: /타이레놀 외 2개 접기/ })).toHaveAttribute('aria-expanded', 'true');
  await expect.poll(() => requestedEpisodeId).toBe('42');
  await expect(page.getByText('42번 처방 메모')).toBeVisible();
});

test('처방 인벤토리 조회가 실패하면 오류를 보이고 다시 시도해 아코디언을 복원한다', async ({ page }) => {
  let attempts = 0;
  let allowOptions = false;
  await page.route('**/api/v1/med/notes/episodes**', (route) => {
    attempts += 1;
    if (!allowOptions) return fulfillJson(route, { message: '조회 실패' }, 500);
    return fulfillJson(route, EPISODES);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [NOTE_41], total: 1, nextCursor: null }),
  );

  await page.goto('/medications/notes');

  await expect(page.getByRole('alert').first()).toContainText('메모가 있는 처방을 불러오지 못했어요');
  const failedAttempts = attempts;
  allowOptions = true;
  await page.getByRole('button', { name: '다시 시도' }).first().click();
  await page.getByRole('tab', { name: '메모 있는 처방' }).click();
  await expect(page.getByRole('button', { name: /아목시실린 펼치기/ })).toBeVisible();
  expect(attempts).toBeGreaterThan(failedAttempts);
});

test('이전 effect 세대의 처방 옵션 응답이 최신 세대 응답을 덮지 않는다', async ({ page }) => {
  let optionRequests = 0;
  let releaseOldResponse: (() => void) | undefined;
  const oldResponseCanFinish = new Promise<void>((resolve) => {
    releaseOldResponse = resolve;
  });
  await page.route('**/api/v1/med/notes/episodes**', async (route) => {
    optionRequests += 1;
    if (optionRequests === 1) {
      await oldResponseCanFinish;
      await fulfillJson(route, [{
        careEpisodeId: 71,
        alias: '이전 세대 처방',
        startDate: '2026-01-01',
        status: 'ACTIVE',
      }]);
      return;
    }
    await fulfillJson(route, [{
      careEpisodeId: 72,
      alias: '최신 세대 처방',
      startDate: '2026-02-01',
      status: 'ACTIVE',
    }]);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [], total: 0, nextCursor: null }),
  );

  await page.goto('/medications/notes');
  await expect.poll(() => optionRequests).toBeGreaterThan(1);
  await expect(page.getByText('최신 세대 처방')).toBeVisible();
  const oldResponseFinished = page.waitForResponse((response) => response.url().includes('/api/v1/med/notes/episodes'));
  releaseOldResponse?.();
  await (await oldResponseFinished).finished();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByText('최신 세대 처방')).toBeVisible();
  await expect(page.getByText('이전 세대 처방')).toHaveCount(0);
});

test('세션이 종료되면 이전 계정의 대기 중인 처방 옵션을 노출하지 않는다', async ({ page }) => {
  let optionRequests = 0;
  let releaseOldResponse: (() => void) | undefined;
  const oldResponseCanFinish = new Promise<void>((resolve) => {
    releaseOldResponse = resolve;
  });
  await page.route('**/api/v1/med/notes/episodes**', async (route) => {
    optionRequests += 1;
    await oldResponseCanFinish;
    await fulfillJson(route, [{
      careEpisodeId: 71,
      alias: '이전 계정 처방',
      startDate: '2026-01-01',
      status: 'ACTIVE',
    }]);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [], total: 0, nextCursor: null }),
  );

  await page.goto('/medications/notes');
  await expect.poll(() => optionRequests).toBeGreaterThan(0);
  await page.evaluate(() => window.dispatchEvent(new Event('poke:auth-session-expired')));
  const oldResponseFinished = page.waitForResponse((response) => response.url().includes('/api/v1/med/notes/episodes'));
  releaseOldResponse?.();
  await (await oldResponseFinished).finished();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText('이전 계정 처방')).toHaveCount(0);
});
