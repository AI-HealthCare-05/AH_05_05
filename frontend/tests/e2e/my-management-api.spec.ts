import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

async function chooseTime(page: Page, hour: string, minute: string) {
  const sheet = page.getByRole('dialog', { name: '시간 선택' });
  await sheet.getByLabel('시').click();
  await page.getByRole('option', { name: `${hour}시`, exact: true }).click();
  await sheet.getByLabel('분').click();
  await page.getByRole('option', { name: `${minute}분`, exact: true }).click();
}

test('설정 API 시간은 HH:MM으로 보이고 한 필드 PATCH는 camelCase를 유지한다', async ({
  page,
}) => {
  const patchBodies: unknown[] = [];
  const response = {
    notifyMedication: false,
    notifySupplement: false,
    notifyConsentedAt: null,
    morningMedicationTime: '08:00:00',
    lunchMedicationTime: '13:00:00',
    eveningMedicationTime: '19:00:00',
    bedtimeMedicationTime: '22:00:00',
  };
  await page.route('**/api/v1/me/settings', async (route) => {
    if (route.request().method() === 'PATCH') {
      patchBodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...response, morningMedicationTime: '08:30:00' }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });

  await page.goto('/dev/medication-alarm-times');
  await page.getByRole('button', { name: /아침약 08:00/ }).click();
  await chooseTime(page, '08', '30');
  await page.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(page.getByRole('button', { name: /아침약 08:30/ })).toBeVisible();
  expect(patchBodies).toEqual([{ morningMedicationTime: '08:30' }]);
});

async function chooseMyTime(
  page: Page,
  slotLabel: string,
  hour: string,
  minute: string,
) {
  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await sheet.getByLabel(slotLabel + ' 시').click();
  await page.getByRole('option', { name: hour + '시', exact: true }).click();
  await sheet.getByLabel(slotLabel + ' 분').click();
  await page.getByRole('option', { name: minute + '분', exact: true }).click();
}

test('마이페이지 알림 시간은 네 필드를 PATCH 한 번으로 저장한다', async ({ page }) => {
  const patchBodies: unknown[] = [];
  const response = {
    notifyMedication: false,
    notifySupplement: false,
    notifyConsentedAt: null,
    morningMedicationTime: '06:00:00',
    lunchMedicationTime: '11:00:00',
    eveningMedicationTime: '17:00:00',
    bedtimeMedicationTime: '21:00:00',
  };
  const updatedResponse = {
    ...response,
    morningMedicationTime: '08:00:00',
    lunchMedicationTime: '13:00:00',
    eveningMedicationTime: '19:00:00',
    bedtimeMedicationTime: '23:00:00',
  };
  let currentResponse = response;
  await page.route('**/api/v1/me/settings', async (route) => {
    if (route.request().method() === 'PATCH') {
      patchBodies.push(route.request().postDataJSON());
      currentResponse = updatedResponse;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(updatedResponse),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(currentResponse),
    });
  });

  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await chooseMyTime(page, '아침', '08', '00');
  await chooseMyTime(page, '점심', '13', '00');
  await chooseMyTime(page, '저녁', '19', '00');
  await chooseMyTime(page, '자기전', '23', '00');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  expect(patchBodies).toEqual([
    {
      morningMedicationTime: '08:00',
      lunchMedicationTime: '13:00',
      eveningMedicationTime: '19:00',
      bedtimeMedicationTime: '23:00',
    },
  ]);
  await expect(page.getByRole('dialog', { name: '알림 시간' })).toHaveCount(0);
  await expect(page.getByText('알림 시간을 바꿨어요.')).toBeVisible();

  await page.reload();
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  const reloadedSheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(reloadedSheet.getByLabel('아침 시')).toContainText('08');
  await expect(reloadedSheet.getByLabel('자기전 시')).toContainText('23');
});

test('마이페이지 시간 순서가 어긋나면 PATCH를 보내지 않는다', async ({ page }) => {
  let patchCount = 0;
  const response = {
    notifyMedication: false,
    notifySupplement: false,
    notifyConsentedAt: null,
    morningMedicationTime: '08:00:00',
    lunchMedicationTime: '13:00:00',
    eveningMedicationTime: '19:00:00',
    bedtimeMedicationTime: '22:00:00',
  };
  await page.route('**/api/v1/me/settings', async (route) => {
    if (route.request().method() === 'PATCH') {
      patchCount += 1;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });

  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await chooseMyTime(page, '아침', '14', '00');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(sheet.getByText('아침 < 점심 < 저녁 < 자기전 순서로 정해주세요')).toBeVisible();
  expect(patchCount).toBe(0);
});
test('마이페이지 알림 시간 PATCH가 실패하면 서버 메시지와 고른 값을 유지한다', async ({
  page,
}) => {
  let patchCount = 0;
  const response = {
    notifyMedication: false,
    notifySupplement: false,
    notifyConsentedAt: null,
    morningMedicationTime: '08:00:00',
    lunchMedicationTime: '13:00:00',
    eveningMedicationTime: '19:00:00',
    bedtimeMedicationTime: '22:00:00',
  };
  await page.route('**/api/v1/me/settings', async (route) => {
    if (route.request().method() === 'PATCH') {
      patchCount += 1;
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'invalid_medication_times',
          message: '서버가 알림 시간 순서를 거부했어요.',
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });

  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await chooseMyTime(page, '아침', '08', '30');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  const sheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('서버가 알림 시간 순서를 거부했어요.')).toBeVisible();
  await expect(sheet.getByLabel('아침 시')).toContainText('08');
  await expect(sheet.getByLabel('아침 분')).toContainText('30');
  expect(patchCount).toBe(1);
});
test('진료일정 목록은 start_date 쿼리와 snake_case 응답을 화면 타입으로 바꾼다', async ({
  page,
}) => {
  let requestUrl: URL | null = null;
  await page.route('**/api/v1/user/follow-up-visits?*', async (route) => {
    requestUrl = new URL(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 41,
            user_id: 7,
            visit_date: '2026-09-21',
            visit_time: '15:30:00',
            hospital: '새봄병원',
            created_at: '2026-09-02T10:00:00+09:00',
            updated_at: null,
          },
        ],
        total: 1,
        offset: 0,
        limit: 100,
      }),
    });
  });

  await page.goto('/dev/my-visits');
  await expect(page.getByRole('button', { name: /9월 21일.*새봄병원.*15:30/ })).toBeVisible();

  expect(requestUrl).not.toBeNull();
  expect(requestUrl!.searchParams.get('start_date')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  expect(requestUrl!.searchParams.get('offset')).toBe('0');
  expect(requestUrl!.searchParams.get('limit')).toBe('100');
});
