import { expect, test, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const NOTE_41 = {
  id: 901, careEpisodeId: 41, careEpisodeAlias: '아침 처방',
  careEpisodeStartDate: '2026-08-01', careEpisodeStatus: 'ACTIVE',
  availableMedications: [{ id: 501, name: '아목시실린', dose: '500mg' }],
  medicationId: 501, medication: { id: 501, name: '아목시실린', dose: '500mg' },
  dosedAt: '2026-08-02T08:00:00', body: '속이 편했어요',
  createdAt: '2026-08-02T08:10:00', updatedAt: null,
};

const EPISODE_41 = {
  careEpisodeId: 41, alias: '아침 처방', startDate: '2026-08-01', status: 'ACTIVE',
  representativeMedicationName: '아목시실린', medicationCount: 1, noteCount: 1,
  medications: NOTE_41.availableMedications,
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-review-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-review@example.com');
  });
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, []));
});

for (const invalidEpisodeId of ['abc', '0']) {
  test(`잘못된 episodeId=${invalidEpisodeId}는 전체 메모를 요청하지 않고 유효한 아코디언 선택으로 복구한다`, async ({ page }) => {
    let listRequests = 0;
    await page.route('**/api/v1/med/notes/episodes**', (route) => fulfillJson(route, [EPISODE_41]));
    await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
      listRequests += 1;
      return fulfillJson(route, { items: [NOTE_41], total: 1, nextCursor: null });
    });

    await page.goto(`/medications/notes?episodeId=${invalidEpisodeId}`);

    await expect(page.getByRole('alert')).toContainText('올바르지 않은 처방 주소예요');
    expect(listRequests).toBe(0);
    await page.getByRole('tab', { name: '작성한 메모' }).click();
    await page.getByRole('button', { name: /아침 처방 .*펼치기/ }).click();
    await expect(page).toHaveURL('/medications/notes?episodeId=41');
    await expect(page.getByText('속이 편했어요')).toBeVisible();
    expect(listRequests).toBe(1);
  });
}

test('상세 삭제가 즉시 401이면 늦은 UI 후속 처리를 하지 않고 로그인으로 이동한다', async ({ page }) => {
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
  await page.route('**/api/v1/med/notes/episodes**', (route) => fulfillJson(route, [EPISODE_41]));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [NOTE_41], total: 1, nextCursor: null }),
  );
  await page.route('**/api/v1/med/notes/901', (route) => {
    if (route.request().method() === 'GET') return fulfillJson(route, NOTE_41);
    requestedIds.push(901);
    return fulfillJson(route, { message: '인증 만료' }, 401);
  });

  await page.goto('/medications/notes?episodeId=41');
  await page.getByRole('button', { name: /속이 편했어요/ }).click();
  await page.getByRole('button', { name: '메모 삭제', exact: true }).click();
  await page.getByRole('button', { name: '삭제하기' }).click();

  await expect(page).toHaveURL(/\/login/);
  expect(requestedIds).toEqual([901]);
});
