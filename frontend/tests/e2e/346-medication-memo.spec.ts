import { mkdirSync } from 'node:fs';
import path from 'node:path';
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

for (const width of [320, 375, 390]) {
  test(`복약 메모 입력은 ${width}px 모바일 폭 안에서 처방과 복용 일시를 유지한다`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.route('**/api/v1/medications', (route) => fulfillJson(route, [OVERVIEW]));
    await page.route(/\/api\/v1\/med\/notes\/episodes(?:\?.*)?$/, (route) => fulfillJson(route, [{
      careEpisodeId: OVERVIEW.recordId,
      alias: OVERVIEW.alias,
      startDate: OVERVIEW.start.date,
      firstDoseAt: `${OVERVIEW.start.date}T${OVERVIEW.mealTimes.evening}:00`,
      status: 'ACTIVE',
      noteCount: 0,
      canCreateNote: true,
      medicationCount: 1,
      representativeMedicationName: OVERVIEW.medications[0].name,
      medications: [{ id: OVERVIEW.medications[0].medicationId, name: OVERVIEW.medications[0].name, dose: OVERVIEW.medications[0].dose }],
    }]));

    await page.goto('/medications/notes/new');
    const prescription = page.getByLabel('처방', { exact: true });
    const takenAt = page.getByLabel('복용 일시');
    await expect(prescription).toBeEnabled();
    await expect(takenAt).toBeEditable();

    const geometry = await page.evaluate(() => {
      const viewport = document.documentElement.clientWidth;
      const fields = [
        document.querySelector<HTMLSelectElement>("select[aria-label='처방']")!,
        document.querySelector<HTMLInputElement>("input[aria-label='복용 일시']")!,
      ];
      return {
        overflow: document.documentElement.scrollWidth - viewport,
        fieldsFit: fields.every((field) => {
          const box = field.getBoundingClientRect();
          return box.left >= 0 && box.right <= viewport;
        }),
        matchingWidths: Math.abs(fields[0].getBoundingClientRect().width - fields[1].getBoundingClientRect().width) < 1,
      };
    });
    expect(geometry).toEqual({ overflow: 0, fieldsFit: true, matchingWidths: true });

    const directory = process.env.UI520_SCREENSHOT_DIR;
    if (directory && width === 390) {
      mkdirSync(directory, { recursive: true });
      await page.screenshot({
        path: path.join(directory, 'medication-note-390.png'),
        fullPage: true,
      });
    }
  });
}

test('새 메모는 선택한 처방의 첫 복용 일시를 수정 가능한 기본값으로 보여준다', async ({ page }) => {
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [OVERVIEW]));

  await page.goto('/medications/notes/new');
  const doseDateTime = page.getByLabel('복용 일시');
  await expect(doseDateTime).toBeEditable();
  await expect(doseDateTime).toHaveValue('');
  await page.getByLabel('처방').selectOption('24');
  await expect(doseDateTime).toHaveValue('2026-08-24 19:40');
});

test('새 메모에서 수정한 복용 일시를 생성 요청에 보낸다', async ({ page }) => {
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
  await page.getByLabel('처방').selectOption('24');
  await expect(page.getByLabel('복용 일시')).toHaveValue('2026-08-24 19:40');
  await page.getByLabel('복용 일시').fill('2026-08-26T21:10');
  await page.getByLabel('복용 후 느낀 점').fill('자동 일시 메모');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect.poll(() => createPayload).toEqual({
    careEpisodeId: 24,
    medicationId: 501,
    dosedAt: '2026-08-26T21:10',
    body: '자동 일시 메모',
  });
});

test('처방 시작 시간대를 확인할 수 없으면 빈 입력에 사용자가 직접 입력해 저장한다', async ({ page }) => {
  let createPayload: unknown;
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [{
    ...OVERVIEW,
    mealTimes: {
      morning: '08:00',
      lunch: '13:00',
      bedtime: '22:30',
    },
  }]));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, async (route) => {
    if (route.request().method() === 'POST') {
      createPayload = route.request().postDataJSON();
      await fulfillJson(route, {
        ...EXISTING_NOTE,
        dosedAt: '2026-08-26T07:25:00',
        body: '직접 입력한 메모',
      });
      return;
    }
    await fulfillJson(route, { items: [], total: 0, nextCursor: null });
  });

  await page.goto('/medications/notes/new');
  await page.getByLabel('처방').selectOption('24');
  const doseDateTime = page.getByLabel('복용 일시');
  await expect(doseDateTime).toHaveValue('');
  await doseDateTime.fill('2026-08-26T07:25');
  await page.getByLabel('복용 후 느낀 점').fill('직접 입력한 메모');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect.poll(() => createPayload).toEqual({
    careEpisodeId: 24,
    medicationId: 501,
    dosedAt: '2026-08-26T07:25',
    body: '직접 입력한 메모',
  });
});

test('기존 메모의 복용 일시도 계속 수정할 수 있다', async ({ page }) => {
  let updatePayload: unknown;
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [OVERVIEW]));
  await page.route('**/api/v1/med/notes/404', async (route) => {
    if (route.request().method() === 'PATCH') {
      updatePayload = route.request().postDataJSON();
      await fulfillJson(route, {
        ...EXISTING_NOTE,
        dosedAt: '2026-08-26T10:30:00',
        body: '일시도 수정한 메모',
      });
      return;
    }
    await fulfillJson(route, EXISTING_NOTE);
  });
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) =>
    fulfillJson(route, { items: [], total: 0, nextCursor: null }),
  );

  await page.goto('/medications/notes/404');
  await expect(page.getByLabel('복용 일시')).toHaveValue('2026-08-25 09:15');
  await page.getByLabel('복용 일시').fill('2026-08-26T10:30');
  await page.getByLabel('복용 후 느낀 점').fill('일시도 수정한 메모');
  await page.getByRole('button', { name: '수정 저장', exact: true }).click();

  await expect.poll(() => updatePayload).toEqual({
    medicationId: 501,
    dosedAt: '2026-08-26T10:30',
    body: '일시도 수정한 메모',
  });
});

test('상세 수정 화면에서는 삭제 버튼을 제거하고 수정 저장을 유지한다', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [OVERVIEW]));
  await page.route('**/api/v1/med/notes/404', (route) => fulfillJson(route, EXISTING_NOTE));

  await page.goto('/medications/notes/404');
  const editButton = page.getByRole('button', { name: '수정 저장', exact: true });
  const deleteButton = page.getByRole('button', { name: '삭제', exact: true });
  await expect(editButton).toBeVisible();
  await expect(deleteButton).toHaveCount(0);

  const editBox = await editButton.boundingBox();
  expect(editBox).not.toBeNull();
  expect(editBox!.height).toBeGreaterThanOrEqual(44);
  expect(editBox!.width).toBeGreaterThan(300);
});
