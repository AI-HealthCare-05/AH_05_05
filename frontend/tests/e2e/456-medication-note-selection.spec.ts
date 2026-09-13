import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

const currentEpisode = {
  careEpisodeId: 501,
  alias: '현재 복용 처방',
  startDate: '2026-09-13',
  firstDoseAt: '2026-09-13T08:00:00',
  status: 'ACTIVE',
  representativeMedicationName: '현재약',
  medicationCount: 1,
  noteCount: 0,
  canCreateNote: true,
  medications: [{ id: 5001, name: '현재약', dose: '10mg' }],
};

const endedEpisode = {
  careEpisodeId: 502,
  alias: '지난 처방',
  startDate: '2026-09-01',
  firstDoseAt: '2026-09-01T08:00:00',
  status: 'ACTIVE',
  representativeMedicationName: '지난약',
  medicationCount: 1,
  noteCount: 2,
  canCreateNote: false,
  medications: [{ id: 5002, name: '지난약', dose: '20mg' }],
};

const deletedEpisode = {
  careEpisodeId: 503,
  alias: '삭제한 처방',
  startDate: '2026-09-02',
  firstDoseAt: '2026-09-02T08:00:00',
  status: 'CANCELLED',
  representativeMedicationName: '삭제약',
  medicationCount: 1,
  noteCount: 1,
  canCreateNote: false,
  medications: [{ id: 5003, name: '삭제약', dose: '30mg' }],
};

function note(id: number, episode = endedEpisode) {
  return {
    id,
    careEpisodeId: episode.careEpisodeId,
    careEpisodeAlias: episode.alias,
    careEpisodeStartDate: episode.startDate,
    careEpisodeStatus: episode.status,
    availableMedications: episode.medications,
    medicationId: null,
    medication: null,
    dosedAt: `2026-09-0${id - 6000}T08:00:00+09:00`,
    body: `보존된 건강상태 ${id}`,
    createdAt: '2026-09-03T08:10:00+09:00',
    updatedAt: null,
  };
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-13T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-456-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-456@example.com');
  });
  await page.route(/^https:\/\/(?!127\.0\.0\.1:45547).*/, route => route.abort());
});

for (const width of [320, 390]) {
  test(`메모 헤더는 열 개 선택해도 제목과 버튼이 잘리지 않는다 (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.route('**/api/v1/**', route => fulfillJson(route, { code: 'FIXTURE_MISSING', message: 'fixture missing' }, 503));
    await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, route => fulfillJson(route, [{ ...endedEpisode, noteCount: 10 }]));
    await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, route => fulfillJson(route, {
      items: Array.from({ length: 10 }, (_, index) => ({ ...note(6001 + index), dosedAt: '2026-09-03T08:00:00+09:00' })),
      total: 10, nextCursor: null,
    }));
    await page.goto('/medications/notes');
    await page.getByRole('tab', { name: '작성한 메모' }).click();
    await page.getByRole('button', { name: /지난 처방.*펼치기/ }).click();
    const banner = page.getByRole('banner');
    await banner.getByRole('button', { name: '선택', exact: true }).click();
    for (const checkbox of await page.getByRole('checkbox').all()) await checkbox.check();
    await expect(banner.getByRole('button', { name: '삭제 10개', exact: true })).toBeVisible();
    await expect(page.getByRole('main').getByRole('group', { name: '복약 메모 선택' })).toHaveCount(0);
    const geometry = await banner.evaluate((element) => {
      const title = element.querySelector('h1')!;
      const back = element.querySelector('button')!.getBoundingClientRect();
      return { titleFits: title.scrollWidth <= title.clientWidth, backWidth: back.width, noOverflow: document.documentElement.scrollWidth <= innerWidth };
    });
    expect(geometry).toEqual({ titleFits: true, backWidth: 44, noOverflow: true });
    const directory = process.env.UI456_MEMO_SCREENSHOT_DIR;
    if (directory) {
      mkdirSync(directory, { recursive: true });
      await banner.scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(directory, `memo-header-selection-${width}.png`), animations: 'disabled' });
    }
  });
}

test('작성 목록은 현재 복용 기간만 열고 지난·삭제 처방의 기존 메모는 계속 보여 준다', async ({ page }) => {
  await page.route('**/api/v1/**', route => fulfillJson(route, { code: 'FIXTURE_MISSING', message: 'fixture missing' }, 503));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, route =>
    fulfillJson(route, [currentEpisode, endedEpisode, deletedEpisode]));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, route => {
    const episodeId = new URL(route.request().url()).searchParams.get('episodeId');
    const items = episodeId === '502' ? [note(6001), note(6002)] :
      episodeId === '503' ? [note(6003, deletedEpisode)] : [];
    return fulfillJson(route, { items, total: items.length, nextCursor: null });
  });

  await page.goto('/medications/notes');

  await expect(page.getByRole('banner').getByRole('button', { name: '선택', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '새 메모 작성' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /현재 복용 처방.*펼치기/ })).toBeVisible();
  await expect(page.getByText('지난 처방', { exact: true })).toHaveCount(0);
  await expect(page.getByText('삭제한 처방', { exact: true })).toHaveCount(0);
  await page.getByRole('tab', { name: '작성한 메모' }).click();
  await expect(page.getByRole('banner').getByRole('button', { name: '선택', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '선택', exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: /지난 처방.*펼치기/ }).click();
  await expect(page.getByText('보존된 건강상태 6001')).toBeVisible();
  await expect(page.getByRole('button', { name: '이 처방에 새 메모' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /삭제한 처방.*펼치기/ })).toBeVisible();
});

test('메모 선택 취소는 기록을 보존하고 부분 실패 뒤 실패한 항목만 다시 삭제한다', async ({ page }) => {
  let secondDeleteAttempts = 0;
  const remainingIds = new Set([6001, 6002]);
  await page.route('**/api/v1/**', route => fulfillJson(route, { code: 'FIXTURE_MISSING', message: 'fixture missing' }, 503));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, route =>
    fulfillJson(route, [{ ...endedEpisode, noteCount: remainingIds.size }]));
  await page.route(/\/api\/v1\/med\/notes\/\d+$/, route => {
    const id = Number(route.request().url().split('/').pop());
    if (route.request().method() !== 'DELETE') return fulfillJson(route, note(id));
    if (id === 6002 && secondDeleteAttempts++ === 0) {
      return fulfillJson(route, { code: 'DELETE_FAILED', message: '삭제 실패' }, 500);
    }
    remainingIds.delete(id);
    return route.fulfill({ status: 204 });
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, route => {
    const items = [...remainingIds].map(id => note(id));
    return fulfillJson(route, { items, total: items.length, nextCursor: null });
  });

  await page.goto('/medications/notes?episodeId=502');
  await expect(page.getByRole('heading', { name: '복약 메모', exact: true })).toBeVisible();
  await page.getByRole('banner').getByRole('button', { name: '선택', exact: true }).click();
  await expect(page.getByRole('button', { name: '새 메모 작성' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /삭제 \d+개/ })).toHaveCount(0);
  await page.getByRole('checkbox', { name: /보존된 건강상태 6001 선택/ }).check();
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page.getByText('보존된 건강상태 6001')).toBeVisible();

  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox', { name: /보존된 건강상태 6001 선택/ }).check();
  await page.getByRole('checkbox', { name: /보존된 건강상태 6002 선택/ }).check();
  await page.getByRole('button', { name: '삭제 2개', exact: true }).click();
  await page.getByRole('button', { name: '삭제하기', exact: true }).click();

  await expect(page.getByText('보존된 건강상태 6001')).toHaveCount(0);
  await expect(page.getByText('보존된 건강상태 6002')).toBeVisible();
  await expect(page.getByRole('checkbox', { name: /보존된 건강상태 6002 선택/ })).toBeChecked();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
  await page.getByRole('button', { name: '삭제하기', exact: true }).click();
  await expect.poll(() => [...remainingIds]).toEqual([]);
  await expect(page.getByRole('button', { name: '선택', exact: true })).toHaveCount(0);
  await expect(page.getByText('작성한 건강상태 기록이 아직 없어요.')).toBeVisible();
});

test('선택 모드는 처방을 바꾸어도 유지하고 여러 처방의 메모를 합산해 삭제한다', async ({ page }) => {
  const deletedIds: number[] = [];
  await page.route('**/api/v1/**', route => fulfillJson(route, { code: 'FIXTURE_MISSING', message: 'fixture missing' }, 503));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, route =>
    fulfillJson(route, [{ ...endedEpisode, noteCount: 1 }, { ...deletedEpisode, noteCount: 1 }]));
  await page.route(/\/api\/v1\/med\/notes\/\d+$/, route => {
    const id = Number(route.request().url().split('/').pop());
    if (route.request().method() === 'DELETE') {
      deletedIds.push(id);
      return route.fulfill({ status: 204 });
    }
    return fulfillJson(route, id === 6003 ? note(id, deletedEpisode) : note(id));
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, route => {
    const episodeId = new URL(route.request().url()).searchParams.get('episodeId');
    const items = episodeId === '503' ? [note(6003, deletedEpisode)] : [note(6001)];
    return fulfillJson(route, { items, total: 1, nextCursor: null });
  });

  await page.goto('/medications/notes');
  await page.getByRole('tab', { name: '작성한 메모' }).click();
  await page.getByRole('button', { name: /지난 처방.*펼치기/ }).click();
  await page.getByRole('banner').getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox', { name: /보존된 건강상태 6001 선택/ }).check();
  await page.getByRole('button', { name: /삭제한 처방.*펼치기/ }).click();
  await expect(page.getByRole('banner').getByRole('button', { name: '삭제 1개', exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: /보존된 건강상태 6003 선택/ }).check();
  await page.getByRole('banner').getByRole('button', { name: '삭제 2개', exact: true }).click();
  await page.getByRole('button', { name: '삭제하기', exact: true }).click();
  await expect.poll(() => deletedIds).toEqual([6001, 6003]);
});

test('삭제 전에 시작한 더 보기 응답은 삭제 개수를 되돌리지 않는다', async ({ page }) => {
  let releaseStalePage!: () => void;
  const stalePageCanFinish = new Promise<void>((resolve) => { releaseStalePage = resolve; });
  let loadMoreAttempts = 0;
  await page.route('**/api/v1/**', route => fulfillJson(route, { code: 'FIXTURE_MISSING', message: 'fixture missing' }, 503));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, route =>
    fulfillJson(route, [{ ...endedEpisode, noteCount: 2 }]));
  await page.route(/\/api\/v1\/med\/notes\/\d+$/, route => {
    if (route.request().method() === 'DELETE') return route.fulfill({ status: 204 });
    return fulfillJson(route, note(6001));
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, async route => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    if (!cursor) {
      return fulfillJson(route, { items: [note(6001)], total: 2, nextCursor: 'older-page' });
    }
    loadMoreAttempts += 1;
    if (loadMoreAttempts === 1) {
      await stalePageCanFinish;
      return fulfillJson(route, { items: [note(6002)], total: 2, nextCursor: null });
    }
    return fulfillJson(route, { items: [note(6002)], total: 1, nextCursor: null });
  });

  await page.goto('/medications/notes?episodeId=502');
  await expect(page.getByRole('heading', { name: '건강상태 기록 2개' })).toBeVisible();
  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await page.getByRole('banner').getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox', { name: /보존된 건강상태 6001 선택/ }).check();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
  await page.getByRole('button', { name: '삭제하기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '건강상태 기록 1개' })).toBeVisible();

  const staleResponse = page.waitForResponse(response =>
    response.url().includes('cursor=older-page') && response.request().method() === 'GET');
  releaseStalePage();
  await staleResponse;
  await expect(page.getByRole('heading', { name: '건강상태 기록 1개' })).toBeVisible();
  await expect(page.getByText('보존된 건강상태 6002')).toHaveCount(0);
  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await expect(page.getByText('보존된 건강상태 6002')).toBeVisible();
  await expect(page.getByRole('heading', { name: '건강상태 기록 1개' })).toBeVisible();
});

test('새 메모 처방 선택기는 작성 불가 inventory와 종료 overview를 제외한다', async ({ page }) => {
  await page.route('**/api/v1/**', route => fulfillJson(route, { code: 'FIXTURE_MISSING', message: 'fixture missing' }, 503));
  await page.route('**/api/v1/medications', route => fulfillJson(route, [
    {
      recordId: 501, alias: '현재 복용 처방', documentImageUrl: '',
      start: { date: '2026-09-13', slot: 'morning' }, endDate: '2026-09-13',
      daysRemaining: 1, isFinished: false,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
      medications: [{ medicationId: 5001, name: '현재약', dose: '10mg', days: 1, daysRemaining: 1, slots: ['morning'], asNeeded: false }],
    },
    {
      recordId: 502, alias: '지난 처방', documentImageUrl: '',
      start: { date: '2026-09-01', slot: 'morning' }, endDate: '2026-09-03',
      daysRemaining: 0, isFinished: true,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
      medications: [{ medicationId: 5002, name: '지난약', dose: '20mg', days: 3, daysRemaining: 0, slots: ['morning'], asNeeded: false }],
    },
    {
      recordId: 504, alias: '미래 처방', documentImageUrl: '',
      start: { date: '2026-09-14', slot: 'morning' }, endDate: '2026-09-16',
      daysRemaining: 3, isFinished: false,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
      medications: [{ medicationId: 5004, name: '미래약', dose: '40mg', days: 3, daysRemaining: 3, slots: ['morning'], asNeeded: false }],
    },
  ]));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, route =>
    fulfillJson(route, [currentEpisode, endedEpisode, deletedEpisode]));

  await page.goto('/medications/notes/new');

  await expect(page.getByLabel('처방', { exact: true }).locator('option')).toHaveText([
    '처방을 선택해주세요',
    '현재 복용 처방',
  ]);
  await page.getByLabel('처방', { exact: true }).selectOption('501');
  await expect(page.getByLabel('복용 일시')).toHaveValue('2026-09-13T08:00');
});
