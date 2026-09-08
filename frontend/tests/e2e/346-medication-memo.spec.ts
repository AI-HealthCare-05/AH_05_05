import { expect, test, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const OVERVIEW = {
  recordId: 24,
  alias: '저녁 처방',
  documentImageUrl: '/api/v1/ocr/jobs/24/image',
  start: { date: '2026-08-24', slot: 'evening' },
  endDate: '2026-08-28',
  daysRemaining: 3,
  isFinished: false,
  mealTimes: {
    morning: '08:00',
    lunch: '13:00',
    evening: '19:40',
    bedtime: '22:30',
  },
  medications: [
    {
      medicationId: 501,
      name: '아목시실린',
      dose: '500mg',
      days: 5,
      daysRemaining: 3,
      slots: ['evening'],
      asNeeded: false,
    },
  ],
};

const EXISTING_NOTE = {
  id: 404,
  careEpisodeId: 24,
  careEpisodeAlias: '저녁 처방',
  careEpisodeStartDate: '2026-08-24',
  careEpisodeStatus: 'ACTIVE',
  availableMedications: [{ id: 501, name: '아목시실린', dose: '500mg' }],
  medicationId: 501,
  medication: { id: 501, name: '아목시실린', dose: '500mg' },
  dosedAt: '2026-08-25T09:15:00',
  body: '기존 메모',
  createdAt: '2026-08-25T09:15:00',
  updatedAt: null,
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-note-346-token');
    sessionStorage.setItem('poke.account-principal', 'medication-note-346@example.com');
  });
});

test('새 메모는 선택한 처방의 첫 복용 일시를 자동 저장하고 날짜 입력을 노출하지 않는다', async ({ page }) => {
  let createPayload: unknown;
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [OVERVIEW]));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, async (route) => {
    if (route.request().method() === 'POST') {
      createPayload = route.request().postDataJSON();
      await fulfillJson(route, {
        ...EXISTING_NOTE,
        dosedAt: '2026-08-24T19:40:00',
        body: '자동 일시 메모',
      });
      return;
    }
    await fulfillJson(route, { items: [], total: 0, nextCursor: null });
  });

  await page.goto('/medications/notes/new');
  await expect(page.locator('input[type="datetime-local"]')).toHaveCount(0);
  await page.getByLabel('처방').selectOption('24');
  await expect(page.getByText('2026년 8월 24일 19:40', { exact: true })).toBeVisible();
  await page.getByLabel('복용 후 느낀 점').fill('자동 일시 메모');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect.poll(() => createPayload).toEqual({
    careEpisodeId: 24,
    medicationId: 501,
    dosedAt: '2026-08-24T19:40',
    body: '자동 일시 메모',
  });
});

test('처방 시작 시간대를 확인할 수 없으면 임의의 일시 없이 저장을 막는다', async ({ page }) => {
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [{
    ...OVERVIEW,
    mealTimes: {
      morning: '08:00',
      lunch: '13:00',
      bedtime: '22:30',
    },
  }]));

  await page.goto('/medications/notes/new');
  await page.getByLabel('처방').selectOption('24');

  await expect(page.getByRole('alert')).toContainText('처방의 시작 날짜와 시간대');
  await expect(page.getByRole('button', { name: '저장', exact: true })).toBeDisabled();
});

test('수정과 삭제 버튼은 같은 행에서 가용 폭을 반씩 쓰고 터치 높이를 유지한다', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [OVERVIEW]));
  await page.route('**/api/v1/med/notes/404', (route) => fulfillJson(route, EXISTING_NOTE));

  await page.goto('/medications/notes/404');
  const editButton = page.getByRole('button', { name: '수정 저장', exact: true });
  const deleteButton = page.getByRole('button', { name: '삭제', exact: true });
  await expect(editButton).toBeVisible();
  await expect(deleteButton).toBeVisible();

  const editBox = await editButton.boundingBox();
  const deleteBox = await deleteButton.boundingBox();
  expect(editBox).not.toBeNull();
  expect(deleteBox).not.toBeNull();
  expect(Math.abs(editBox!.y - deleteBox!.y)).toBeLessThan(1);
  expect(Math.abs(editBox!.width - deleteBox!.width)).toBeLessThan(1);
  expect(editBox!.height).toBeGreaterThanOrEqual(44);
  expect(deleteBox!.height).toBeGreaterThanOrEqual(44);
});
