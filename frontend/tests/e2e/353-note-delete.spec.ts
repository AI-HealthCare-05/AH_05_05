import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const NOTES = [
  {
    id: 901, careEpisodeId: 41, careEpisodeAlias: '아침 처방',
    careEpisodeStartDate: '2026-08-01', careEpisodeStatus: 'ACTIVE',
    availableMedications: [{ id: 501, name: '아목시실린', dose: '500mg' }],
    medicationId: 501, medication: { id: 501, name: '아목시실린', dose: '500mg' },
    dosedAt: '2026-08-02T08:00:00', body: '속이 편했어요',
    createdAt: '2026-08-02T08:10:00', updatedAt: null,
  },
  {
    id: 902, careEpisodeId: 42, careEpisodeAlias: '저녁 처방',
    careEpisodeStartDate: '2026-08-03', careEpisodeStatus: 'COMPLETED',
    availableMedications: [{ id: 502, name: '타이레놀', dose: '500mg' }],
    medicationId: 502, medication: { id: 502, name: '타이레놀', dose: '500mg' },
    dosedAt: '2026-08-04T19:00:00', body: '어지러움이 있었어요',
    createdAt: '2026-08-04T19:10:00', updatedAt: null,
  },
];

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockNoteList(page: Page) {
  let notes = [...NOTES];
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/med/notes/episodes**', (route) => fulfillJson(route, NOTES.map((note) => ({
    careEpisodeId: note.careEpisodeId,
    alias: note.careEpisodeAlias,
    startDate: note.careEpisodeStartDate,
    status: note.careEpisodeStatus,
    noteCount: notes.some((item) => item.careEpisodeId === note.careEpisodeId) ? 1 : 0,
    representativeMedicationName: note.medication.name,
    medicationCount: 1,
    medications: note.availableMedications,
  }))));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const episodeId = Number(new URL(route.request().url()).searchParams.get('episodeId'));
    const items = notes.filter((note) => !episodeId || note.careEpisodeId === episodeId);
    return fulfillJson(route, { items, total: items.length, nextCursor: null });
  });
  await page.route(/\/api\/v1\/med\/notes\/(901|902)$/, (route) => {
    const id = Number(route.request().url().split('/').at(-1));
    if (route.request().method() === 'GET') return fulfillJson(route, notes.find((note) => note.id === id));
    if (route.request().method() === 'DELETE') {
      notes = notes.filter((note) => note.id !== id);
      return fulfillJson(route, {});
    }
    return route.fallback();
  });
}

async function openNote(page: Page, name: string, body: string) {
  await page.goto('/medications/notes');
  await page.getByRole('tab', { name: '메모 있는 처방' }).click();
  await page.getByRole('button', { name: new RegExp(`${name} .*펼치기`) }).click();
  await page.getByRole('button', { name: new RegExp(body) }).click();
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-353-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-353@example.com');
  });
});

test('상세 화면에서 확인 후 삭제하면 마지막 메모인 처방을 메모 없는 탭으로 옮긴다', async ({ page }) => {
  await mockNoteList(page);
  await openNote(page, '아침 처방', '속이 편했어요');

  await page.getByRole('button', { name: '메모 삭제', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('이 복약 메모를 삭제할까요?');
  await page.getByRole('button', { name: '삭제하기' }).click();

  await expect(page).toHaveURL('/medications/notes?episodeId=41');
  await expect(page.getByRole('tab', { name: '메모 없는 처방' })).toHaveAttribute('data-state', 'active');
  await expect(page.getByRole('button', { name: /아침 처방 .*접기/ })).toBeVisible();
  await expect(page.getByText('속이 편했어요')).toHaveCount(0);
});

test('상세 삭제가 실패하면 확인창에서 오류를 보여주고 같은 메모를 재시도한다', async ({ page }) => {
  let attempts = 0;
  await mockNoteList(page);
  await page.route('**/api/v1/med/notes/901', async (route) => {
    if (route.request().method() !== 'DELETE') return route.fallback();
    attempts += 1;
    if (attempts === 1) return fulfillJson(route, { message: '일시적인 오류' }, 500);
    return fulfillJson(route, {});
  });
  await openNote(page, '아침 처방', '속이 편했어요');
  await page.getByRole('button', { name: '메모 삭제', exact: true }).click();
  await page.getByRole('button', { name: '삭제하기' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('alert')).toContainText('일시적인 오류');
  await dialog.getByRole('button', { name: '다시 시도' }).click();
  await expect.poll(() => attempts).toBe(2);
  await expect(dialog).toHaveCount(0);
});

test('삭제 응답을 기다리는 중 세션이 끝나면 늦은 성공이 이전 계정 목록으로 이동시키지 않는다', async ({ page }) => {
  let releaseDelete!: () => void;
  const canFinish = new Promise<void>((resolve) => { releaseDelete = resolve; });
  await mockNoteList(page);
  await page.route('**/api/v1/med/notes/901', async (route) => {
    if (route.request().method() !== 'DELETE') return route.fallback();
    await canFinish;
    return fulfillJson(route, {});
  });
  await openNote(page, '아침 처방', '속이 편했어요');
  await page.getByRole('button', { name: '메모 삭제', exact: true }).click();
  const requested = page.waitForRequest((request) => request.method() === 'DELETE');
  await page.getByRole('button', { name: '삭제하기' }).click();
  await requested;
  await page.evaluate(() => window.dispatchEvent(new Event('poke:auth-session-expired')));
  const deleteFinished = page.waitForResponse((response) => response.request().method() === 'DELETE');
  releaseDelete();
  await (await deleteFinished).finished();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));

  await expect(page).toHaveURL(/\/login/);
  await expect(page).not.toHaveURL('/medications/notes');
});
