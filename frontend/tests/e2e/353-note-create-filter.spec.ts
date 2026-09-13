import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const episodes = [
  { careEpisodeId: 41, alias: '아침 처방', startDate: '2026-08-01', status: 'ACTIVE' },
  { careEpisodeId: 42, alias: '저녁 처방', startDate: '2026-08-02', status: 'ACTIVE' },
];
const overviews = episodes.map((episode) => ({
  recordId: episode.careEpisodeId, alias: episode.alias, documentImageUrl: '',
  start: { date: episode.startDate, slot: 'morning' }, endDate: '2026-08-10',
  daysRemaining: 5, isFinished: false,
  mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
  medications: [{
    medicationId: episode.careEpisodeId * 10, name: `${episode.alias} 약`, dose: '1정',
    days: 10, daysRemaining: 5, slots: ['morning'], asNeeded: false,
  }],
}));

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'note-create-filter-test');
    sessionStorage.setItem('poke.account-principal', 'note-create-filter@example.com');
  });
  const notes: Record<string, unknown>[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    let body: unknown = [];
    if (url.pathname === '/api/v1/medications') body = overviews;
    else if (url.pathname === '/api/v1/med/notes/episodes') body = episodes.map((episode) => ({
      ...episode,
      noteCount: notes.filter((note) => note.careEpisodeId === episode.careEpisodeId).length,
      medicationCount: 1,
      representativeMedicationName: `${episode.alias} 약`,
      medications: [{ id: episode.careEpisodeId * 10, name: `${episode.alias} 약`, dose: '1정' }],
    }));
    else if (url.pathname === '/api/v1/med/notes' && route.request().method() === 'POST') {
      const payload = route.request().postDataJSON();
      const episode = episodes.find((item) => item.careEpisodeId === payload.careEpisodeId)!;
      body = {
        id: 901 + notes.length, ...payload, careEpisodeAlias: episode.alias,
        careEpisodeStartDate: episode.startDate, careEpisodeStatus: 'ACTIVE',
        availableMedications: [], medicationId: payload.medicationId ?? null, medication: null,
        createdAt: '2026-08-03T09:00:00', updatedAt: null,
      };
      notes.push(body as Record<string, unknown>);
    } else if (url.pathname === '/api/v1/med/notes') {
      const filter = url.searchParams.get('episodeId');
      const items = notes.filter((note) => !filter || String(note.careEpisodeId) === filter);
      body = { items, total: items.length, nextCursor: null };
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
});

async function openNewNote(page: Page, episodeId: string | null = '41', hasNotes = false, episodeName?: string) {
  await page.goto('/dev/home-empty');
  await page.getByRole('navigation', { name: '주요 화면' }).getByRole('button', { name: '복약', exact: true }).click();
  await page.getByRole('button', { name: '복약 메모', exact: true }).click();
  if (episodeId !== null) {
    if (hasNotes) await page.getByRole('tab', { name: '작성한 메모' }).click();
    const episode = episodes.find((item) => String(item.careEpisodeId) === episodeId);
    await page.getByRole('button', { name: new RegExp(`${episodeName ?? episode?.alias ?? '지난 처방'} .*펼치기`) }).click();
    await page.getByRole('button', { name: hasNotes ? '이 처방에 새 메모' : '이 처방에 메모 작성' }).click();
  } else {
    await page.getByRole('button', { name: '새 메모 작성' }).click();
  }
  await expect(page.getByLabel('처방', { exact: true })).toBeEnabled();
}

test('아코디언의 처방으로 새 메모를 열면 처방과 복용 일시를 채우고 전체 처방을 기본값으로 둔다', async ({ page }) => {
  await openNewNote(page);
  await expect(page.getByLabel('처방', { exact: true })).toHaveValue('41');
  await expect(page.getByLabel('약', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('복용 일시')).toHaveValue('2026-08-01T08:00');
});

for (const chosenEpisode of ['41', '42']) {
  test(`새 메모를 처방 ${chosenEpisode}에 저장하면 그 필터 목록으로 돌아가고 뒤로가기 이력을 보존한다`, async ({ page }) => {
    await openNewNote(page);
    await page.getByLabel('처방', { exact: true }).selectOption(chosenEpisode);
    await page.getByLabel('건강상태 기록').fill('저장한 새 메모');
    await page.getByRole('button', { name: '저장', exact: true }).click();
    await expect(page).toHaveURL(`/medications/notes?episodeId=${chosenEpisode}`);
    await expect(page.getByRole('tab', { name: '작성한 메모' })).toHaveAttribute('data-state', 'active');
    await expect(page.getByRole('button', { name: new RegExp(`${chosenEpisode === '41' ? '아침' : '저녁'} 처방 .*접기`) })).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByText('저장한 새 메모')).toBeVisible();
    await page.getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL('/medications');
    await page.getByRole('button', { name: '뒤로 가기' }).click();
    await expect(page).toHaveURL('/dev/home-empty');
  });
}

test('새 메모의 처방을 바꾸고 취소하면 원래 목록 아코디언을 유지한다', async ({ page }) => {
  await openNewNote(page);
  await page.getByLabel('처방', { exact: true }).selectOption('42');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=41');
  await expect(page.getByRole('button', { name: /아침 처방 .*접기/ })).toHaveAttribute('aria-expanded', 'true');
});

test('전체 목록에서 작성한 새 메모도 저장한 처방 필터로 이동한다', async ({ page }) => {
  await openNewNote(page, null);
  await expect(page.getByLabel('처방', { exact: true })).toHaveValue('');
  await page.getByLabel('처방', { exact: true }).selectOption('42');
  await page.getByLabel('건강상태 기록').fill('전체 목록에서 작성');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=42');
  await expect(page.getByText('전체 목록에서 작성')).toBeVisible();
});

test('저장 응답 전에 취소하면 늦은 응답이 원래 필터를 바꾸지 않는다', async ({ page }) => {
  let releaseSave!: () => void;
  const canFinish = new Promise<void>((resolve) => { releaseSave = resolve; });
  await page.route('**/api/v1/med/notes', async (route) => {
    if (route.request().method() === 'POST') await canFinish;
    await route.fallback();
  });
  await openNewNote(page);
  await page.getByLabel('처방', { exact: true }).selectOption('42');
  await page.getByLabel('건강상태 기록').fill('늦은 저장');
  const requested = page.waitForRequest((request) => request.method() === 'POST' && request.url().endsWith('/api/v1/med/notes'));
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await requested;
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=41');
  const responded = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/api/v1/med/notes'));
  releaseSave();
  await (await responded).finished();
  await expect(page).toHaveURL('/medications/notes?episodeId=41');
  await expect(page.getByRole('button', { name: /아침 처방 .*접기/ })).toHaveAttribute('aria-expanded', 'true');
});

test('새 메모 화면을 새로고침한 뒤 저장해도 저장한 처방 필터로 돌아간다', async ({ page }) => {
  await openNewNote(page);
  await page.reload();
  await page.getByLabel('처방', { exact: true }).selectOption('42');
  await page.getByLabel('건강상태 기록').fill('새로고침 후 저장');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=42');
  await expect(page.getByRole('tab', { name: '작성한 메모' })).toHaveAttribute('data-state', 'active');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL('/medications');
});

for (const status of ['COMPLETED', 'CANCELLED']) {
  test(`${status} 과거 처방 필터에서 작성하면 활성 목록에 없어도 원래 처방을 선택하고 메모 본문은 비워 둔다`, async ({ page }) => {
    const oldNote = {
      id: 9909, careEpisodeId: 41, careEpisodeAlias: '지난 처방',
      careEpisodeStartDate: '2025-01-01', careEpisodeStatus: status,
      availableMedications: [{ id: 410, name: '지난 처방 약', dose: '1정' }],
      medicationId: 410, medication: { id: 410, name: '지난 처방 약', dose: '1정' },
      dosedAt: '2025-01-02T08:00:00', body: '새 메모에 복사하면 안 되는 기존 내용',
      createdAt: '2025-01-02T09:00:00', updatedAt: null,
    };
    await page.route('**/api/v1/medications', (route) => route.fulfill({ json: [overviews[1]] }));
    await page.route('**/api/v1/med/notes/9909', (route) => route.fulfill({ json: oldNote }));
    await page.route('**/api/v1/med/notes/episodes**', (route) => route.fulfill({ json: [
      {
        careEpisodeId: 41, alias: '지난 처방', startDate: '2025-01-01', status,
        noteCount: 1, medicationCount: 1, representativeMedicationName: '지난 처방 약',
        medications: [{ id: 410, name: '지난 처방 약', dose: '1정' }],
      },
      { ...episodes[1], noteCount: 0, medicationCount: 1, representativeMedicationName: '저녁 처방 약', medications: [{ id: 420, name: '저녁 처방 약', dose: '1정' }] },
    ] }));
    await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      return route.fulfill({ json: { items: [oldNote], total: 1, nextCursor: null } });
    });
    await openNewNote(page, '41', true, '지난 처방');
    await expect(page.getByLabel('처방', { exact: true })).toHaveValue('41');
    await expect(page.getByLabel('약', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('건강상태 기록')).toHaveValue('');
    await page.getByLabel('복용 일시').fill('2025-01-03T09:00');
    await page.getByLabel('건강상태 기록').fill('과거 처방에 작성한 새 메모');
    await page.getByRole('button', { name: '저장', exact: true }).click();
    await expect(page).toHaveURL('/medications/notes?episodeId=41');
  });
}

test('목록 인벤토리에 약이 없으면 기존 메모를 참고해 새 메모의 처방을 복원한다', async ({ page }) => {
  let fallbackRequests = 0;
  await page.route('**/api/v1/medications', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/notes/episodes**', (route) => route.fulfill({ json: [{
    ...episodes[0], noteCount: 0, medicationCount: 0, representativeMedicationName: null, medications: [],
  }] }));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get('episodeId') === '41' && url.searchParams.get('limit') === '1') {
      fallbackRequests += 1;
    }
    const items = url.searchParams.get('episodeId') === '41' && url.searchParams.get('limit') === '1' ? [{
      id: 9909, careEpisodeId: 41, careEpisodeAlias: '지난 처방', careEpisodeStartDate: '2025-01-01',
      careEpisodeStatus: 'COMPLETED', availableMedications: [], medicationId: null, medication: null,
      dosedAt: '2025-01-02T08:00:00', body: '기존 메모', createdAt: '2025-01-02T09:00:00', updatedAt: null,
    }] : [];
    return route.fulfill({ json: { items, total: items.length, nextCursor: null } });
  });
  await openNewNote(page);
  await expect(page.getByLabel('처방', { exact: true })).toHaveValue('41');
  await expect(page.getByLabel('건강상태 기록')).toHaveValue('');
  expect(fallbackRequests).toBe(1);
});
