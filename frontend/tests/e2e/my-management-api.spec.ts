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

test('예약 알림은 ACTIVE exact query를 보내고 snake_case 응답을 가까운 순서로 정렬한다', async ({
  page,
}) => {
  let requestUrl: URL | null = null;
  await page.route('**/api/v1/alarms?*', async (route) => {
    requestUrl = new URL(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 1,
            user_id: 7,
            care_episode_id: null,
            source_guide_id: null,
            follow_up_visit_id: 41,
            alarm_type: 'FOLLOW_UP_VISIT',
            meal_slot: null,
            title: '나중 알림',
            message: null,
            scheduled_at: '2026-09-05T10:00:00+09:00',
            recurrence_rule: null,
            status: 'ACTIVE',
          },
          {
            id: 2,
            user_id: 7,
            care_episode_id: null,
            source_guide_id: null,
            follow_up_visit_id: null,
            alarm_type: 'MEDICATION',
            meal_slot: 'MORNING',
            title: '가까운 알림',
            message: '약을 복용할 시간입니다.',
            scheduled_at: '2026-09-03T08:00:00+09:00',
            recurrence_rule: 'FREQ=DAILY;COUNT=3',
            status: 'ACTIVE',
          },
        ],
        total: 2,
        offset: 0,
        limit: 100,
      }),
    });
  });

  await page.goto('/dev/my-alarms');
  await expect(page.getByRole('heading', { name: '가까운 알림' })).toBeVisible();
  const titles = await page.locator('article h2').allTextContents();

  expect(requestUrl).not.toBeNull();
  expect(requestUrl!.searchParams.get('status')).toBe('ACTIVE');
  expect(requestUrl!.searchParams.get('offset')).toBe('0');
  expect(requestUrl!.searchParams.get('limit')).toBe('100');
  expect(titles).toEqual(['가까운 알림', '나중 알림']);
});
