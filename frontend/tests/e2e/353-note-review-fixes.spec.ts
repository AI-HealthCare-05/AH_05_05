import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const NOTE_41 = {
  id: 901,
  careEpisodeId: 41,
  careEpisodeAlias: '아침 처방',
  careEpisodeStartDate: '2026-08-01',
  careEpisodeStatus: 'ACTIVE',
  availableMedications: [{ id: 501, name: '아목시실린', dose: '500mg' }],
  medicationId: 501,
  medication: { id: 501, name: '아목시실린', dose: '500mg' },
  dosedAt: '2026-08-02T08:00:00',
  body: '속이 편했어요',
  createdAt: '2026-08-02T08:10:00',
  updatedAt: null,
};

const NOTE_42 = {
  ...NOTE_41,
  id: 902,
  careEpisodeId: 42,
  careEpisodeAlias: '저녁 처방',
  careEpisodeStartDate: '2026-08-03',
  careEpisodeStatus: 'COMPLETED',
  medicationId: 502,
  medication: { id: 502, name: '타이레놀', dose: '500mg' },
  availableMedications: [{ id: 502, name: '타이레놀', dose: '500mg' }],
  body: '어지러움이 있었어요',
};

const EPISODE_41 = {
  careEpisodeId: 41,
  alias: '아침 처방',
  startDate: '2026-08-01',
  status: 'ACTIVE',
};

const EPISODE_42 = {
  careEpisodeId: 42,
  alias: '저녁 처방',
  startDate: '2026-08-03',
  status: 'COMPLETED',
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function selectNotes(page: Page, ids: number[]) {
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  for (const id of ids) {
    await page.getByRole('checkbox', { name: `메모 선택: ${id}` }).check();
  }
  await page.getByRole('button', { name: `선택한 ${ids.length}개 삭제` }).click();
  await page.getByRole('button', { name: '삭제하기' }).click();
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-review-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-review@example.com');
  });
});

for (const invalidEpisodeId of ['abc', '0']) {
  test(`잘못된 episodeId=${invalidEpisodeId}는 전체 메모를 요청하지 않고 전체 선택으로 복구한다`, async ({ page }) => {
    let listRequests = 0;
    await page.route('**/api/v1/med/notes/episodes', (route) => fulfillJson(route, [EPISODE_41]));
    await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
      listRequests += 1;
      return fulfillJson(route, { items: [NOTE_41], total: 1, nextCursor: null });
    });

    await page.goto(`/medications/notes?episodeId=${invalidEpisodeId}`);

    const selector = page.getByLabel('처방별 메모 필터');
    await expect(selector).toBeEnabled();
    await expect(page.getByRole('heading', { name: '복약 메모 0개' })).toBeVisible();
    await expect(page.getByRole('alert')).toContainText('올바르지 않은 처방 필터');
    expect(listRequests).toBe(0);
    await expect(selector).toHaveValue('__invalid_episode__');

    await selector.selectOption('');
    await expect(page).toHaveURL('/medications/notes');
    await expect(page.getByText('속이 편했어요')).toBeVisible();
    expect(listRequests).toBe(1);
  });
}

test('선택한 처방의 마지막 메모 삭제 후 옵션을 재조회하고 양수 딥링크 표시는 유지한다', async ({ page }) => {
  let noteDeleted = false;
  let postDeleteOptionRequests = 0;
  await page.route('**/api/v1/med/notes/episodes', (route) => {
    if (noteDeleted) {
      postDeleteOptionRequests += 1;
      return fulfillJson(route, []);
    }
    return fulfillJson(route, [EPISODE_41]);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [NOTE_41], total: 1, nextCursor: null }),
  );
  await page.route('**/api/v1/med/notes/901', (route) => {
    noteDeleted = true;
    return fulfillJson(route, {});
  });

  await page.goto('/medications/notes?episodeId=41');
  await selectNotes(page, [901]);

  await expect.poll(() => postDeleteOptionRequests).toBe(1);
  const selector = page.getByLabel('처방별 메모 필터');
  await expect(selector).toHaveValue('41');
  await expect(selector.locator('option')).toHaveText(['전체', '처방 #41']);
  await expect(page.getByRole('heading', { name: '복약 메모 0개' })).toBeVisible();
});

test('부분 삭제 성공 뒤 옵션 재조회 실패를 알리고 다시 시도한다', async ({ page }) => {
  let successfulDeleteHappened = false;
  let postDeleteOptionRequests = 0;
  await page.route('**/api/v1/med/notes/episodes', (route) => {
    if (!successfulDeleteHappened) return fulfillJson(route, [EPISODE_41, EPISODE_42]);
    postDeleteOptionRequests += 1;
    if (postDeleteOptionRequests === 1) return fulfillJson(route, { message: '조회 실패' }, 500);
    return fulfillJson(route, [EPISODE_42]);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [NOTE_41, NOTE_42], total: 2, nextCursor: null }),
  );
  await page.route('**/api/v1/med/notes/901', (route) => {
    successfulDeleteHappened = true;
    return fulfillJson(route, {});
  });
  await page.route('**/api/v1/med/notes/902', (route) =>
    fulfillJson(route, { message: '삭제 실패' }, 500),
  );

  await page.goto('/medications/notes');
  await selectNotes(page, [901, 902]);

  await expect.poll(() => postDeleteOptionRequests).toBe(1);
  await expect(page.getByText('필터용 처방 목록을 불러오지 못했어요.')).toBeVisible();
  await page.getByRole('button', { name: '처방 목록 다시 시도' }).click();
  await expect.poll(() => postDeleteOptionRequests).toBe(2);
  await expect(page.getByLabel('처방별 메모 필터')).toContainText('저녁 처방');
  await expect(page.getByText('속이 편했어요')).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: '메모 선택: 902' })).toBeChecked();
});

test('첫 삭제가 즉시 401이면 React 세션 반영 전에도 다음 삭제를 보내지 않는다', async ({ page }) => {
  const requestedIds: number[] = [];
  await page.addInitScript(() => {
    const dispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      if (event.type === 'poke:auth-session-expired') {
        window.setTimeout(() => dispatch(event), 200);
        return true;
      }
      return dispatch(event);
    }) as typeof window.dispatchEvent;
  });
  await page.route('**/api/v1/med/notes/episodes', (route) =>
    fulfillJson(route, [EPISODE_41, EPISODE_42]),
  );
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [NOTE_41, NOTE_42], total: 2, nextCursor: null }),
  );
  await page.route(/\/api\/v1\/med\/notes\/(901|902)$/, (route) => {
    const id = Number(route.request().url().split('/').at(-1));
    requestedIds.push(id);
    return fulfillJson(route, id === 901 ? { message: '인증 만료' } : {}, id === 901 ? 401 : 200);
  });

  await page.goto('/medications/notes');
  await selectNotes(page, [901, 902]);

  await expect(page).toHaveURL(/\/login/);
  expect(requestedIds).toEqual([901]);
});

test('더 보기와 삭제 선택 모드는 서로의 진행 중 요청과 겹치지 않는다', async ({ page }) => {
  let releaseMore: (() => void) | undefined;
  const moreCanFinish = new Promise<void>((resolve) => {
    releaseMore = resolve;
  });
  let moreRequested = false;
  await page.route('**/api/v1/med/notes/episodes', (route) =>
    fulfillJson(route, [EPISODE_41, EPISODE_42]),
  );
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    if (cursor === 'page-2') {
      moreRequested = true;
      await moreCanFinish;
      return fulfillJson(route, { items: [NOTE_42], total: 3, nextCursor: 'page-3' });
    }
    return fulfillJson(route, { items: [NOTE_41], total: 2, nextCursor: 'page-2' });
  });

  await page.goto('/medications/notes');
  await page.getByRole('button', { name: '더 보기' }).click();
  await expect.poll(() => moreRequested).toBe(true);
  await expect(page.getByRole('button', { name: '삭제', exact: true })).toBeDisabled();

  releaseMore?.();
  await expect(page.getByText('어지러움이 있었어요')).toBeVisible();
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('button', { name: '더 보기' })).toBeDisabled();
});
