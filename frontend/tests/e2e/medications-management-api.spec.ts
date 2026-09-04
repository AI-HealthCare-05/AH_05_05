import { expect, test, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const MEAL_TIMES = {
  morning: '08:00',
  lunch: '13:00',
  evening: '19:00',
  bedtime: '22:30',
};

function overview(recordId: number, isFinished: boolean, daysRemaining: number) {
  return {
    recordId,
    documentImageUrl: `/api/v1/ocr/jobs/${recordId}/image`,
    start: { date: recordId === 12 ? '2026-08-22' : '2026-08-24', slot: 'morning' },
    endDate: recordId === 12 ? '2026-08-31' : '2026-08-28',
    daysRemaining,
    isFinished,
    mealTimes: MEAL_TIMES,
    medications: [
      {
        medicationId: recordId * 10,
        name: recordId === 12 ? '셀레콕시브' : '아목시실린',
        dose: recordId === 12 ? '200mg' : '500mg',
        days: 7,
        daysRemaining,
        slots: ['morning'],
        asNeeded: false,
      },
    ],
  };
}

function manyOverviews(count = 41) {
  return Array.from({ length: count }, (_, index) => {
    const item = overview(1_000 + index, true, 0);
    const startDate = new Date(2026, 7, 24 - index);
    const date = [
      startDate.getFullYear(),
      String(startDate.getMonth() + 1).padStart(2, '0'),
      String(startDate.getDate()).padStart(2, '0'),
    ].join('-');
    return { ...item, start: { ...item.start, date }, endDate: date };
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-management-token');
    sessionStorage.setItem('poke.account-principal', 'medication-management@example.com');
  });
});

test('완료 상태는 daysRemaining이 아니라 서버 isFinished만 따른다', async ({ page }) => {
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [overview(12, false, 0), overview(24, true, 7)]),
  );
  await page.goto('/medications');

  await expect(page.getByRole('button', { name: /2026년 8월 22일 처방.*복용 중/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /2026년 8월 24일 처방.*복용 완료/ })).toBeVisible();
});

test('URL의 조회 범위를 그대로 전달하고 약봉투 이미지는 요청하지 않는다', async ({ page }) => {
  const overviewRequests: URL[] = [];
  let imageRequests = 0;
  await page.route('**/api/v1/medications*', async (route) => {
    const url = new URL(route.request().url());
    if (/\/medications\/\d+$/.test(url.pathname)) {
      await route.continue();
      return;
    }
    overviewRequests.push(url);
    await fulfillJson(route, [overview(12, false, 3)]);
  });
  await page.route('**/api/v1/ocr/jobs/12/image', async (route) => {
    imageRequests += 1;
    await route.fulfill({ status: 200, contentType: 'image/png', body: 'image' });
  });

  await page.goto('/medications?from=2026-08-01&to=2026-08-31');
  await expect.poll(() => overviewRequests.length).toBe(1);
  expect(overviewRequests[0].searchParams.get('from')).toBe('2026-08-01');
  expect(overviewRequests[0].searchParams.get('to')).toBe('2026-08-31');

  await page.getByRole('button', { name: /2026년 8월 22일 처방/ }).click();
  await expect(page.getByRole('button', { name: '약봉투 사진 보기' })).toHaveCount(0);
  expect(imageRequests).toBe(0);
});

test('느린 회차 저장 중 반복 클릭해도 일정 저장 요청은 한 번만 보낸다', async ({ page }) => {
  let saveCalls = 0;
  let savePayload: unknown;
  let releaseSave!: () => void;
  const saveSettled = new Promise<void>((resolve) => {
    releaseSave = resolve;
  });
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [overview(12, false, 3)]),
  );
  await page.route('**/api/v1/med/medication/schedule/12', async (route) => {
    if (route.request().method() !== 'PUT') {
      await route.continue();
      return;
    }
    saveCalls += 1;
    savePayload = route.request().postDataJSON();
    await saveSettled;
    await fulfillJson(route, { saved: true });
  });

  await page.goto('/medications');
  await page.getByRole('button', { name: /2026년 8월 22일 처방/ }).click();
  const dialog = page.getByRole('dialog');
  const saveButton = dialog.getByRole('button', { name: /저장/ });
  await expect(saveButton).toHaveText('저장');
  await saveButton.click();

  await expect(saveButton).toBeDisabled();
  await expect(dialog.getByRole('button', { name: '저장 중...', exact: true })).toBeVisible();
  await saveButton.evaluate((button) => {
    // disabled 속성을 우회한 프로그램적 click도 중복 저장을 만들면 안 됩니다.
    button.removeAttribute('disabled');
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  await expect.poll(() => saveCalls).toBe(1);

  expect(savePayload).toEqual({
    start: { date: '2026-08-22', slot: 'morning' },
    mealTimes: {
      morning: '08:00',
      lunch: '13:00',
      evening: '19:00',
      bedtime: '22:30',
    },
    medications: [{ medicationId: 120, slots: ['morning'] }],
  });
  releaseSave();
  await expect(page.getByText('처방을 저장했어요.')).toBeVisible();
  await expect(dialog).toHaveCount(0);
  expect(saveCalls).toBe(1);
});

test('전체 목록을 한 번 호출해 모두 표시하고 삭제 결과를 반영한다', async ({ page }) => {
  let overviewRequests = 0;
  await page.route('**/api/v1/medications', async (route) => {
    overviewRequests += 1;
    await fulfillJson(route, manyOverviews());
  });
  await page.route('**/api/v1/medications/*', (route) => route.fulfill({ status: 204 }));

  await page.goto('/medications');
  const cards = page.getByRole('button', { name: /처방 · 약/ });
  await expect(cards).toHaveCount(41);

  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await page.getByRole('checkbox').first().check();
  await page.getByRole('button', { name: '삭제하기' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '삭제하기' }).click();

  await expect(page.getByText('1개를 삭제했어요')).toBeVisible();
  await expect(page.getByText('40개', { exact: true })).toBeVisible();
  await expect(cards).toHaveCount(40);
  expect(overviewRequests).toBe(1);
});

test('선택 삭제는 순차 실행하고 부분 실패 항목만 선택 상태로 남긴다', async ({ page }) => {
  const deleteOrder: number[] = [];
  let firstCompleted = false;
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [overview(12, false, 3), overview(24, true, 7)]),
  );
  await page.route('**/api/v1/medications/*', async (route) => {
    const id = Number(new URL(route.request().url()).pathname.split('/').at(-1));
    deleteOrder.push(id);
    if (id === 12) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      firstCompleted = true;
      await route.fulfill({ status: 204 });
      return;
    }
    expect(firstCompleted).toBe(true);
    await fulfillJson(route, { code: 'SERVER_ERROR', message: '실패' }, 500);
  });

  await page.goto('/medications');
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ }).check();
  await page.getByRole('checkbox', { name: /2026년 8월 24일 처방 선택/ }).check();
  await page.getByRole('button', { name: '삭제하기' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '삭제하기' }).click();

  await expect(page.getByText('1개를 삭제했어요. 1개는 실패했어요')).toBeVisible();
  await expect(page.getByRole('checkbox', { name: /2026년 8월 24일 처방 선택/ })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ })).toHaveCount(0);
  expect(deleteOrder).toEqual([12, 24]);
});

test('선택 삭제가 전부 실패하면 같은 항목들을 순서대로 재시도한다', async ({ page }) => {
  const deleteOrder: number[] = [];
  const attempts = new Map<number, number>();
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [overview(12, false, 3), overview(24, true, 7)]),
  );
  await page.route('**/api/v1/medications/*', async (route) => {
    const id = Number(new URL(route.request().url()).pathname.split('/').at(-1));
    const attempt = (attempts.get(id) ?? 0) + 1;
    attempts.set(id, attempt);
    deleteOrder.push(id);
    if (attempt === 1) {
      await fulfillJson(route, { code: 'SERVER_ERROR', message: '실패' }, 500);
      return;
    }
    await route.fulfill({ status: 204 });
  });

  await page.goto('/medications');
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ }).check();
  await page.getByRole('checkbox', { name: /2026년 8월 24일 처방 선택/ }).check();
  await page.getByRole('button', { name: '삭제하기' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: '삭제하기' }).click();

  await expect(dialog).toContainText('선택한 복약 정보를 삭제하지 못했어요. 다시 시도해주세요.');
  await expect(page.locator('button[role="checkbox"][data-state="checked"]')).toHaveCount(2);
  await dialog.getByRole('button', { name: '다시 시도' }).click();

  await expect(page.getByText('2개를 삭제했어요')).toBeVisible();
  await expect(page.getByText('이 기간에 등록한 처방이 없어요')).toBeVisible();
  expect(deleteOrder).toEqual([12, 24, 12, 24]);
});
