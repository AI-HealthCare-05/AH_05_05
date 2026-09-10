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

function schedule(recordId: number, timesPerDay: number, slots = ['morning']) {
  return {
    start: { date: '2026-08-22', slot: 'morning' },
    mealTimes: MEAL_TIMES,
    medications: [
      {
        medicationId: recordId * 10,
        name: '셀레콕시브',
        dose: '200mg',
        timesPerDay,
        timing: '식후',
        slots,
      },
    ],
  };
}

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.route('**/api/v1/user/challenges', (route) =>
    fulfillJson(route, { items: [], total_count: 0 }),
  );
  await page.route('**/api/v1/med/medication/schedule/*', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    const recordId = Number(new URL(route.request().url()).pathname.split('/').at(-1));
    await fulfillJson(route, schedule(recordId, 1));
  });
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'medication-management-token');
    sessionStorage.setItem('poke.account-principal', 'medication-management@example.com');
  });
});

test('처방 편집은 원본 하루 횟수까지만 선택하고 기존 시간을 바꿀 수 있다', async ({ page }) => {
  let scheduleLoads = 0;
  let savedPayload: unknown;
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [overview(12, false, 3)]),
  );
  await page.route('**/api/v1/med/medication/schedule/12', async (route) => {
    if (route.request().method() === 'GET') {
      scheduleLoads += 1;
      await fulfillJson(route, schedule(12, 1));
      return;
    }
    savedPayload = route.request().postDataJSON();
    await fulfillJson(route, { saved: true });
  });
  await page.route('**/api/v1/med/episodes/12/alias', (route) => route.fulfill({ status: 204 }));

  await page.goto('/medications');
  await page.getByRole('button', { name: '처방 수정 · 2026년 8월 22일', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '처방 편집' });
  const morning = dialog.getByRole('button', { name: '셀레콕시브 아침약' });
  const lunch = dialog.getByRole('button', { name: '셀레콕시브 점심약' });
  await expect.poll(() => scheduleLoads).toBe(1);
  await expect(dialog.getByText('하루 1회', { exact: true })).toBeVisible();

  await lunch.click();
  await expect(morning).toHaveAttribute('aria-pressed', 'true');
  await expect(lunch).toHaveAttribute('aria-pressed', 'false');
  await expect(dialog.getByRole('alert')).toHaveText(
    '하루 1회만 선택할 수 있어요. 선택한 시간을 취소한 뒤 다른 시간을 선택해주세요.',
  );

  await morning.click();
  await lunch.click();
  await expect(morning).toHaveAttribute('aria-pressed', 'false');
  await expect(lunch).toHaveAttribute('aria-pressed', 'true');
  await dialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByText('처방을 저장했어요.')).toBeVisible();
  expect(savedPayload).toEqual({
    start: { date: '2026-08-22', slot: 'morning' },
    mealTimes: MEAL_TIMES,
    medications: [{ medicationId: 120, slots: ['lunch'] }],
  });
});

test('원본 횟수 조회 중이거나 실패하면 편집 저장을 막고 재시도한다', async ({ page }) => {
  let attempts = 0;
  let releaseFirstLoad!: () => void;
  const firstLoadReleased = new Promise<void>((resolve) => {
    releaseFirstLoad = resolve;
  });
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [overview(12, false, 3)]),
  );
  await page.route('**/api/v1/med/medication/schedule/12', async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await firstLoadReleased;
      await fulfillJson(route, { code: 'SERVER_ERROR', message: '서버 내부 오류' }, 500);
      return;
    }
    await fulfillJson(route, schedule(12, 1));
  });

  await page.goto('/medications');
  await page.getByRole('button', { name: '처방 수정 · 2026년 8월 22일', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '처방 편집' });
  const morning = dialog.getByRole('button', { name: '셀레콕시브 아침약' });
  const save = dialog.getByRole('button', { name: '저장', exact: true });
  await expect(dialog.getByRole('status')).toHaveText('처방 복용 횟수를 확인하고 있어요.');
  await expect(morning).toBeDisabled();
  await expect(save).toBeDisabled();

  releaseFirstLoad();
  const loadError = dialog.getByRole('alert');
  await expect(loadError).toContainText('처방 복용 횟수를 불러오지 못했어요.');
  await expect(morning).toBeDisabled();
  await expect(save).toBeDisabled();

  await loadError.getByRole('button', { name: '다시 시도' }).click();
  await expect(dialog.getByText('하루 1회', { exact: true })).toBeVisible();
  await expect(morning).toBeEnabled();
  await expect(save).toBeEnabled();
  expect(attempts).toBe(2);
});

test('이미 원본 횟수를 넘은 저장값은 자르지 않고 사용자가 바로잡기 전 저장하지 않는다', async ({ page }) => {
  const invalidOverview = overview(12, false, 3);
  invalidOverview.medications[0].slots = ['morning', 'lunch'];
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, [invalidOverview]),
  );
  await page.route('**/api/v1/med/medication/schedule/12', (route) =>
    fulfillJson(route, schedule(12, 1, ['morning', 'lunch'])),
  );

  await page.goto('/medications');
  await page.getByRole('button', { name: '처방 수정 · 2026년 8월 22일', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '처방 편집' });
  const morning = dialog.getByRole('button', { name: '셀레콕시브 아침약' });
  const lunch = dialog.getByRole('button', { name: '셀레콕시브 점심약' });
  const save = dialog.getByRole('button', { name: '저장', exact: true });
  await expect(dialog.getByText('하루 1회', { exact: true })).toBeVisible();
  await expect(morning).toHaveAttribute('aria-pressed', 'true');
  await expect(lunch).toHaveAttribute('aria-pressed', 'true');
  await expect(dialog.getByRole('alert')).toContainText('하루 1회만 선택할 수 있어요.');
  await expect(save).toBeDisabled();

  await lunch.click();
  await expect(morning).toHaveAttribute('aria-pressed', 'true');
  await expect(lunch).toHaveAttribute('aria-pressed', 'false');
  await expect(dialog.getByRole('alert')).toHaveCount(0);
  await expect(save).toBeEnabled();
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
  // Saving an episode also persists its alias through a separate endpoint.
  await page.route('**/api/v1/med/episodes/12/alias', route => route.fulfill({ status: 204 }));
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
    if (route.request().method() === 'GET') {
      await fulfillJson(route, schedule(12, 1));
      return;
    }
    saveCalls += 1;
    savePayload = route.request().postDataJSON();
    await saveSettled;
    await fulfillJson(route, { saved: true });
  });

  await page.goto('/medications');
  await page.getByRole('button', { name: '처방 수정 · 2026년 8월 22일', exact: true }).click();
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

test('별칭 PATCH 뒤 홈 진입과 재진입은 후속 처방 조회의 별칭을 표시한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.route('**/api/v1/**', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  let alias: string | undefined;
  const aliasPayloads: unknown[] = [];
  await page.route(/\/api\/v1\/medications(?:\?.*)?$/, async (route) => {
    const item = overview(12, false, 3);
    await fulfillJson(route, [{ ...item, ...(alias ? { alias } : {}) }]);
  });
  await page.route('**/api/v1/med/medication/schedule/12', (route) =>
    fulfillJson(route, route.request().method() === 'GET' ? schedule(12, 1) : { saved: true }),
  );
  await page.route('**/api/v1/med/episodes/12/alias', async (route) => {
    const payload = route.request().postDataJSON() as { alias: string | null };
    aliasPayloads.push(payload);
    alias = payload.alias ?? undefined;
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/v1/medications/doses*', (route) => fulfillJson(route, []));
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/medications');
  await page.getByRole('button', { name: '처방 수정 · 2026년 8월 22일', exact: true }).click();
  const episodeDialog = page.getByRole('dialog');
  await episodeDialog.getByLabel('복약 별칭').fill('실 API 홈 별칭');
  await episodeDialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByText('처방을 저장했어요.')).toBeVisible();
  expect(aliasPayloads).toEqual([{ alias: '실 API 홈 별칭' }]);

  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page.getByRole('heading', { name: '실 API 홈 별칭', exact: true })).toBeVisible();
  await page.goto('/medications');
  await expect(page.getByText('실 API 홈 별칭', { exact: true })).toBeVisible();
  await page.goto('/home');
  await expect(page.getByRole('heading', { name: '실 API 홈 별칭', exact: true })).toBeVisible();
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
  await page.getByRole('button', { name: '선택한 처방 삭제', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '삭제하기' }).click();

  await expect(page.getByText('1개를 삭제했어요')).toBeVisible();
  await expect(page.getByText('40개', { exact: true })).toBeVisible();
  await expect(cards).toHaveCount(40);
  expect(overviewRequests).toBe(1);
});

test('긴 별칭과 약 이름은 요약·선택·편집·완료 상세에서 전체가 보인다', async ({ page }) => {
  test.setTimeout(120_000);
  const longAlias = `장기복약관리${'PRESCRIPTION'.repeat(16)}처방`;
  const finishedAlias = `완료복약관리${'FINISHED'.repeat(20)}처방`;
  const longMedication = `복합서방제${'MEDICATION'.repeat(18)}정`;
  const active = {
    ...overview(12, false, 3),
    alias: longAlias,
    medications: [{ ...overview(12, false, 3).medications[0], name: longMedication }],
  };
  const finished = {
    ...overview(24, true, 0),
    alias: finishedAlias,
    medications: [{ ...overview(24, true, 0).medications[0], name: longMedication }],
  };
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [active, finished]));

  async function expectContained(locator: ReturnType<typeof page.locator>, container: ReturnType<typeof page.locator>) {
    await expect(locator).toBeVisible();
    const result = await locator.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return {
        scrollFits: element.scrollWidth <= element.clientWidth + 1,
        heightFits: element.scrollHeight <= element.clientHeight + 1,
        textOverflow: getComputedStyle(element).textOverflow,
        left: rect.left,
        right: rect.right,
      };
    });
    const boundary = await container.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, scrollFits: element.scrollWidth <= element.clientWidth + 1 };
    });
    expect(result.textOverflow).not.toBe('ellipsis');
    expect(result.scrollFits).toBe(true);
    expect(result.heightFits).toBe(true);
    expect(result.left).toBeGreaterThanOrEqual(boundary.left - 1);
    expect(result.right).toBeLessThanOrEqual(boundary.right + 1);
    expect(boundary.scrollFits).toBe(true);
  }

  for (const width of [320, 375, 430, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/medications');
    const activeCard = page.getByRole('button', { name: /2026년 8월 22일 처방/ });
    const activeName = activeCard.getByText(longAlias, { exact: true });
    await expectContained(activeName, activeCard);
    await expect(activeCard.getByText(new RegExp(longMedication))).toHaveCount(0);
    await activeCard.click();
    const details = page.getByRole('region', { name: '2026년 8월 22일 처방 상세' });
    await expectContained(details.getByText(new RegExp(longMedication)), details);
    await activeCard.click();

    await page.getByRole('button', { name: '삭제', exact: true }).click();
    await expect(page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ })).toBeVisible();
    await expectContained(activeName, activeCard);
    await page.getByRole('button', { name: '완료', exact: true }).click();

    await page.getByRole('button', { name: '처방 수정 · 2026년 8월 22일', exact: true }).click();
    const editSheet = page.getByRole('dialog', { name: '처방 편집' });
    const aliasPreview = editSheet.getByLabel('복약 별칭 전체');
    await expect(aliasPreview).toHaveText(longAlias);
    await expectContained(aliasPreview, editSheet);
    const editMedication = editSheet.locator('p').filter({ hasText: longMedication }).first();
    await expectContained(editMedication, editSheet);
    await editSheet.getByRole('button', { name: `${longMedication} 아침약` }).click();
    await expect(editSheet.getByRole('button', { name: `${longMedication} 아침약` })).toHaveAttribute('aria-pressed', 'false');
    await editSheet.getByRole('button', { name: '닫기' }).click();

    await page.getByRole('button', { name: /2026년 8월 24일 처방/ }).click();
    const finishedSheet = page.getByRole('region', { name: '2026년 8월 24일 처방 상세' });
    const finishedCard = page.locator('article').filter({ has: finishedSheet });
    await expectContained(finishedCard.getByText(finishedAlias, { exact: true }), finishedCard);
    await expectContained(finishedSheet.locator('p').filter({ hasText: longMedication }).first(), finishedSheet);
    await page.getByRole('button', { name: /2026년 8월 24일 처방/ }).click();
  }

  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto('/dev/medications');
  const expandableCard = page.getByRole('button', { name: /2026년 8월 22일 처방/ });
  await expandableCard.click();
  await page.getByRole('button', { name: new RegExp(`${longMedication}.*복용 시간 수정`) }).click();
  const slotSheet = page.getByRole('dialog', { name: new RegExp(`${longMedication} 복용 시간`) });
  await expectContained(slotSheet.getByRole('heading'), slotSheet);
  await expect(slotSheet.getByRole('button', { name: `${longMedication} 아침약` })).toBeVisible();
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
  await page.getByRole('button', { name: '선택한 처방 삭제', exact: true }).click();
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
  await page.getByRole('button', { name: '선택한 처방 삭제', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: '삭제하기' }).click();

  await expect(dialog).toContainText('선택한 복약 정보를 삭제하지 못했어요. 다시 시도해주세요.');
  await expect(page.locator('button[role="checkbox"][data-state="checked"]')).toHaveCount(2);
  await dialog.getByRole('button', { name: '다시 시도' }).click();

  await expect(page.getByText('2개를 삭제했어요')).toBeVisible();
  await expect(page.getByText('이 기간에 등록한 처방이 없어요')).toBeVisible();
  expect(deleteOrder).toEqual([12, 24, 12, 24]);
});
