import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const overviews = [
  {
    recordId: 103,
    alias: '저녁 감기 처방',
    documentImageUrl: '/fixtures/103.png',
    start: { date: '2026-09-10', slot: 'evening' },
    endDate: '2026-09-14',
    daysRemaining: 3,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
    medications: [{ medicationId: 1003, name: '타이레놀정500mg', dose: '500mg', days: 5, daysRemaining: 3, slots: ['evening'], asNeeded: false }],
  },
  {
    recordId: 102,
    alias: '점심 처방',
    documentImageUrl: '/fixtures/102.png',
    start: { date: '2026-09-09', slot: 'lunch' },
    endDate: '2026-09-13',
    daysRemaining: 2,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
    medications: [{ medicationId: 1002, name: '아목시실린캡슐', dose: '250mg', days: 5, daysRemaining: 2, slots: ['lunch'], asNeeded: false }],
  },
  {
    recordId: 101,
    alias: '메모 전 아침 처방',
    documentImageUrl: '/fixtures/101.png',
    start: { date: '2026-09-08', slot: 'morning' },
    endDate: '2026-09-12',
    daysRemaining: 1,
    isFinished: false,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
    medications: [{ medicationId: 1001, name: '오메프라졸정20mg', dose: '20mg', days: 5, daysRemaining: 1, slots: ['morning'], asNeeded: false }],
  },
];

const note = {
  id: 9003,
  careEpisodeId: 103,
  careEpisodeAlias: '저녁 감기 처방',
  careEpisodeStartDate: '2026-09-10',
  careEpisodeStatus: 'ACTIVE',
  availableMedications: [{ id: 1003, name: '타이레놀정500mg', dose: '500mg' }],
  medicationId: null,
  medication: null,
  dosedAt: '2026-09-11T19:00:00+09:00',
  body: '열이 내려가고 잠이 잘 왔어요.',
  createdAt: '2026-09-11T19:10:00+09:00',
  updatedAt: null,
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-429-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-429@example.com');
  });
});

test('메모 유무는 전체 처방 메타데이터로 분류하고 처방별 메모는 펼칠 때 페이지를 불러온다', async ({ page }, testInfo) => {
  const noteQueries: string[] = [];
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, overviews));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, (route) => {
    const includeWithoutNotes = new URL(route.request().url()).searchParams.get('includeWithoutNotes') === 'true';
    return fulfillJson(route, [
      { careEpisodeId: 103, alias: '저녁 감기 처방', startDate: '2026-09-10', status: 'ACTIVE', representativeMedicationName: '타이레놀정500mg', medicationCount: 1, noteCount: 21 },
      { careEpisodeId: 102, alias: '점심 처방', startDate: '2026-09-09', status: 'ACTIVE', representativeMedicationName: '아목시실린캡슐', medicationCount: 1, noteCount: 1 },
      ...(includeWithoutNotes ? [
        { careEpisodeId: 101, alias: '메모 전 아침 처방', startDate: '2026-09-08', status: 'ACTIVE', representativeMedicationName: '오메프라졸정20mg', medicationCount: 1, noteCount: 0 },
        { careEpisodeId: 100, alias: '종료된 무메모 처방', startDate: '2026-08-01', status: 'COMPLETED', representativeMedicationName: '세티리진정', medicationCount: 1, noteCount: 0 },
      ] : []),
    ]);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    noteQueries.push(url.search);
    if (url.searchParams.get('episodeId') !== '103') {
      return fulfillJson(route, { items: [], total: 0, nextCursor: null });
    }
    if (url.searchParams.get('cursor') === 'next-103') {
      return fulfillJson(route, {
        items: [{ ...note, id: 9002, body: '둘째 페이지의 건강상태 기록', dosedAt: '2026-09-10T19:00:00+09:00' }],
        total: 21,
        nextCursor: null,
      });
    }
    return fulfillJson(route, { items: [note], total: 21, nextCursor: 'next-103' });
  });

  await page.goto('/medications/notes');

  const noNotesTab = page.getByRole('tab', { name: '메모 없는 처방' });
  const hasNotesTab = page.getByRole('tab', { name: '메모 있는 처방' });
  await expect(noNotesTab).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('button', { name: /메모 전 아침 처방.*펼치기/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /종료된 무메모 처방.*펼치기/ })).toBeVisible();
  await expect(page.getByText('점심 처방')).toHaveCount(0);
  await expect(page.getByText('저녁 감기 처방')).toHaveCount(0);
  expect(noteQueries).toEqual([]);

  await hasNotesTab.click();
  await expect(page.getByRole('button', { name: /점심 처방.*펼치기/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /저녁 감기 처방.*펼치기/ })).toBeVisible();
  await expect(page.getByText('메모 전 아침 처방')).toHaveCount(0);
  await expect(page.getByText('종료된 무메모 처방')).toHaveCount(0);
  expect(noteQueries).toEqual([]);

  await page.getByRole('button', { name: /저녁 감기 처방.*펼치기/ }).click();
  await expect(page.getByText('열이 내려가고 잠이 잘 왔어요.')).toBeVisible();
  expect(noteQueries).toEqual(['?episodeId=103']);

  await page.getByRole('button', { name: '더 보기' }).click();
  await expect(page.getByText('둘째 페이지의 건강상태 기록')).toBeVisible();
  expect(noteQueries).toEqual(['?episodeId=103', '?episodeId=103&cursor=next-103']);
  await page.screenshot({ path: testInfo.outputPath('notes-375.png'), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath('notes-1280.png'), fullPage: true });
});

test('첫 메모를 저장하면 처방이 메모 있는 탭으로 이동한다', async ({ page }) => {
  let created = false;
  const createdNote = {
    ...note,
    id: 9101,
    careEpisodeId: 101,
    careEpisodeAlias: '메모 전 아침 처방',
    availableMedications: [{ id: 1001, name: '오메프라졸정20mg', dose: '20mg' }],
    dosedAt: '2026-09-08T08:00:00',
    body: '속쓰림이 줄었어요.',
  };
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, overviews));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, (route) => fulfillJson(route, [
    {
      careEpisodeId: 101,
      alias: '메모 전 아침 처방',
      startDate: '2026-09-08',
      status: 'ACTIVE',
      representativeMedicationName: '오메프라졸정20mg',
      medicationCount: 1,
      noteCount: created ? 1 : 0,
    },
  ]));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    if (route.request().method() === 'POST') {
      created = true;
      return fulfillJson(route, createdNote, 201);
    }
    return fulfillJson(route, {
      items: created ? [createdNote] : [],
      total: created ? 1 : 0,
      nextCursor: null,
    });
  });

  await page.goto('/medications/notes');
  await page.getByRole('button', { name: /메모 전 아침 처방.*펼치기/ }).click();
  await page.getByRole('button', { name: '이 처방에 메모 작성' }).click();
  await expect(page.getByLabel('약', { exact: true })).toHaveValue('');
  await page.getByLabel('건강상태 기록').fill('속쓰림이 줄었어요.');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect.poll(() => created).toBe(true);
  await expect(page.getByRole('tab', { name: '메모 있는 처방' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('속쓰림이 줄었어요.')).toBeVisible();
});

test('새 메모는 헤더 우측에 있고 작성 폼은 처방 전체와 건강상태 문구를 기본으로 쓴다', async ({ page }) => {
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [overviews[0]]));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, (route) => fulfillJson(route, []));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => fulfillJson(route, { items: [], total: 0, nextCursor: null }));

  await page.goto('/medications/notes');
  const header = page.locator('header');
  const newButton = header.getByRole('button', { name: '새 메모 작성' });
  await expect(newButton).toBeVisible();
  await newButton.click();

  await expect(page.getByRole('heading', { name: '복용시 건강상태 변화를 기록해 보세요.' })).toBeVisible();
  await expect(page.getByLabel('건강상태 기록')).toHaveAttribute(
    'placeholder',
    '건강상태 변화를 작성하여 다음 진료시 의료진과 상담내용으로 활용해보세요.',
  );
  await page.getByLabel('처방', { exact: true }).selectOption('103');
  await expect(page.getByLabel('약', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('약', { exact: true }).locator('option')).toHaveText([
    '처방 전체',
    '타이레놀정500mg',
  ]);
});

test('메모 삭제는 목록이 아니라 수정 상세의 확인 절차에서 수행한다', async ({ page }) => {
  let deleted = false;
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [overviews[0]]));
  await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, (route) => fulfillJson(route, [
    { careEpisodeId: 103, alias: '저녁 감기 처방', startDate: '2026-09-10', status: 'ACTIVE', noteCount: deleted ? 0 : 1 },
  ]));
  await page.route('**/api/v1/med/notes/9003', (route) => {
    if (route.request().method() === 'DELETE') {
      deleted = true;
      return fulfillJson(route, {});
    }
    return fulfillJson(route, note);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => fulfillJson(route, {
    items: deleted ? [] : [note], total: deleted ? 0 : 1, nextCursor: null,
  }));

  await page.goto('/medications/notes?episodeId=103');
  await expect(page.getByRole('button', { name: '삭제', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /저녁 감기 처방.*접기/ })).toBeVisible();
  await page.getByRole('button', { name: '처방 전체 열이 내려가고 잠이 잘 왔어요.' }).click();
  await page.getByRole('button', { name: '메모 삭제' }).click();
  await expect(page.getByRole('dialog')).toContainText('이 복약 메모를 삭제할까요?');
  await page.getByRole('button', { name: '삭제하기' }).click();
  await expect.poll(() => deleted).toBe(true);
  await expect(page).toHaveURL('/medications/notes?episodeId=103');
  await expect(page.getByRole('tab', { name: '메모 없는 처방' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('button', { name: /저녁 감기 처방.*접기/ })).toBeVisible();
});
