import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const NOTES = [
  {
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
  },
  {
    id: 902,
    careEpisodeId: 42,
    careEpisodeAlias: '저녁 처방',
    careEpisodeStartDate: '2026-08-03',
    careEpisodeStatus: 'COMPLETED',
    availableMedications: [{ id: 502, name: '타이레놀', dose: '500mg' }],
    medicationId: 502,
    medication: { id: 502, name: '타이레놀', dose: '500mg' },
    dosedAt: '2026-08-04T19:00:00',
    body: '어지러움이 있었어요',
    createdAt: '2026-08-04T19:10:00',
    updatedAt: null,
  },
];

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockNoteList(page: Page) {
  await page.route('**/api/v1/med/notes/episodes', (route) => fulfillJson(route, [
    { careEpisodeId: 42, alias: '저녁 처방', startDate: '2026-08-03', status: 'COMPLETED' },
    { careEpisodeId: 41, alias: '아침 처방', startDate: '2026-08-01', status: 'ACTIVE' },
  ]));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return fulfillJson(route, { items: NOTES, total: NOTES.length, nextCursor: null });
    }
    return route.fallback();
  });
}

async function selectNotes(page: Page, ids: number[]) {
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  for (const id of ids) {
    await page.getByRole('checkbox', { name: `메모 선택: ${id}` }).check();
  }
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-353-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-353@example.com');
  });
});

test('목록 삭제는 선택과 확인을 거쳐 차례로 요청하고 성공한 메모를 즉시 뺀다', async ({ page }) => {
  const deletedIds: number[] = [];
  await mockNoteList(page);
  await page.route(/\/api\/v1\/med\/notes\/(901|902)$/, async (route) => {
    deletedIds.push(Number(route.request().url().split('/').at(-1)));
    await fulfillJson(route, {});
  });

  await page.goto('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모 2개' })).toBeVisible();
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: '메모 선택: 901' })).toBeVisible();
  await expect(page.getByRole('button', { name: '아침 처방 메모만 보기' })).toHaveCount(0);
  await page.getByRole('button', { name: '완료', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: '메모 선택: 901' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '아침 처방 메모만 보기' })).toHaveCount(0);
  await selectNotes(page, [901, 902]);
  await expect(page).toHaveURL(/\/medications\/notes$/);
  await page.getByRole('button', { name: '선택한 2개 삭제' }).click();
  await expect(page.getByRole('dialog')).toContainText('선택한 복약 메모를 삭제할까요?');
  await page.getByRole('button', { name: '삭제하기' }).click();

  await expect.poll(() => deletedIds).toEqual([901, 902]);
  await expect(page.getByRole('heading', { name: '복약 메모 0개' })).toBeVisible();
  await expect(page.getByText('속이 편했어요')).toHaveCount(0);
  await expect(page.getByText('어지러움이 있었어요')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '삭제', exact: true })).toBeVisible();
});

test('일부 삭제 실패 시 성공한 메모만 빼고 실패한 메모를 선택한 채 재시도한다', async ({ page }) => {
  const deletedIds: number[] = [];
  let note902Attempts = 0;
  await mockNoteList(page);
  await page.route(/\/api\/v1\/med\/notes\/(901|902)$/, async (route) => {
    const id = Number(route.request().url().split('/').at(-1));
    deletedIds.push(id);
    if (id === 902 && note902Attempts++ === 0) {
      await fulfillJson(route, { message: '삭제 실패' }, 500);
      return;
    }
    await fulfillJson(route, {});
  });

  await page.goto('/medications/notes');
  await selectNotes(page, [901, 902]);
  await page.getByRole('button', { name: '선택한 2개 삭제' }).click();
  await page.getByRole('button', { name: '삭제하기' }).click();

  await expect.poll(() => deletedIds).toEqual([901, 902]);
  await expect(page.getByText('속이 편했어요')).toHaveCount(0);
  await expect(page.getByText('어지러움이 있었어요')).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '메모 선택: 902' })).toBeChecked();
  await expect(page.getByRole('button', { name: '선택한 1개 삭제' })).toBeVisible();

  await page.getByRole('button', { name: '선택한 1개 삭제' }).click();
  await page.getByRole('button', { name: '삭제하기' }).click();
  await expect.poll(() => deletedIds).toEqual([901, 902, 902]);
  await expect(page.getByRole('heading', { name: '복약 메모 0개' })).toBeVisible();
});

test('전체 실패하면 확인창에서 오류를 보여주고 동일 대상을 재시도한다', async ({ page }) => {
  let attempts = 0;
  await mockNoteList(page);
  await page.route('**/api/v1/med/notes/901', async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await fulfillJson(route, { message: '일시적인 오류' }, 500);
      return;
    }
    await fulfillJson(route, {});
  });

  await page.goto('/medications/notes');
  await selectNotes(page, [901]);
  await page.getByRole('button', { name: '선택한 1개 삭제' }).click();
  await page.getByRole('button', { name: '삭제하기' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('alert')).toContainText('선택한 복약 메모를 삭제하지 못했어요');
  await dialog.getByRole('button', { name: '다시 시도' }).click();
  await expect.poll(() => attempts).toBe(2);
  await expect(dialog).toHaveCount(0);
});

test('삭제 중 세션이 바뀌면 남은 메모 삭제 요청을 보내지 않는다', async ({ page }) => {
  const requestedIds: number[] = [];
  let releaseFirstDelete: (() => void) | undefined;
  const firstDeleteCanFinish = new Promise<void>((resolve) => {
    releaseFirstDelete = resolve;
  });
  await mockNoteList(page);
  await page.route(/\/api\/v1\/med\/notes\/(901|902)$/, async (route) => {
    const id = Number(route.request().url().split('/').at(-1));
    requestedIds.push(id);
    if (id === 901) await firstDeleteCanFinish;
    await fulfillJson(route, {});
  });

  await page.goto('/medications/notes');
  await selectNotes(page, [901, 902]);
  await page.getByRole('button', { name: '선택한 2개 삭제' }).click();
  await page.getByRole('button', { name: '삭제하기' }).click();
  await expect.poll(() => requestedIds).toEqual([901]);

  await page.evaluate(() => {
    sessionStorage.setItem('poke.account-principal', 'another-account@example.com');
    window.dispatchEvent(new Event('poke:auth-session-expired'));
  });
  releaseFirstDelete?.();

  await expect.poll(() => requestedIds, { timeout: 2_000 }).toEqual([901]);
});
