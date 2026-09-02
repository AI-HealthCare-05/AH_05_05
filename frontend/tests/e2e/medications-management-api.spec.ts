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

test('URL의 조회 범위와 인증된 약봉투 이미지 요청을 그대로 전달한다', async ({ page }) => {
  const overviewRequests: URL[] = [];
  let imageAuthorization = '';
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
    imageAuthorization = route.request().headers().authorization ?? '';
    await route.fulfill({ status: 200, contentType: 'image/png', body: 'image' });
  });

  await page.goto('/medications?from=2026-08-01&to=2026-08-31');
  expect(overviewRequests).toHaveLength(1);
  expect(overviewRequests[0].searchParams.get('from')).toBe('2026-08-01');
  expect(overviewRequests[0].searchParams.get('to')).toBe('2026-08-31');

  await page.getByRole('button', { name: /2026년 8월 22일 처방/ }).click();
  await page.getByRole('button', { name: '약봉투 사진 보기' }).click();
  await expect(page.getByRole('img', { name: '확대한 약봉투 원본' })).toHaveAttribute('src', /^blob:/);
  expect(imageAuthorization).toBe('Bearer medication-management-token');
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
  await expect(page.getByRole('checkbox', { name: /처방 선택/ })).toHaveCount(2);
  await dialog.getByRole('button', { name: '다시 시도' }).click();

  await expect(page.getByText('2개를 삭제했어요')).toBeVisible();
  await expect(page.getByText('이 기간에 등록한 처방이 없어요')).toBeVisible();
  expect(deleteOrder).toEqual([12, 24, 12, 24]);
});
