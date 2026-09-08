import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

const ACCOUNT_A_PROFILE = {
  name: '첫 계정 이름',
  maskedName: '첫**',
  phoneNumber: '01011112222',
  birthDate: '1980-01-01',
  gender: 'FEMALE',
};

const ACCOUNT_B_PROFILE = {
  name: '두 번째 계정 이름',
  maskedName: '두*****',
  phoneNumber: '01033334444',
  birthDate: '1990-02-02',
  gender: 'MALE',
};

function myPageFixture(pathname: string): unknown | undefined {
  if (pathname === '/api/v1/medications') return [];
  if (
    pathname === '/api/v1/med/user-suppl-nutr' ||
    pathname === '/api/v1/user/follow-up-visits'
  ) {
    return { items: [], total: 0, offset: 0, limit: 100 };
  }
  if (pathname === '/api/v1/me/settings') {
    return {
      notifyMedication: false,
      notifySupplement: false,
      notifySchedule: false,
      notifyConsentedAt: null,
      morningMedicationTime: '08:00',
      lunchMedicationTime: '13:00',
      eveningMedicationTime: '19:00',
      bedtimeMedicationTime: '22:00',
    };
  }
  return undefined;
}

test('마이페이지는 공개용 maskedName 대신 내 프로필 name을 보여준다', async ({ page }) => {
  await page.route('**/api/v1/users/me', (route) => route.fulfill({ json: ACCOUNT_A_PROFILE }));

  await page.goto('/dev/my-authenticated');

  await expect(page.getByRole('button', { name: /첫 계정 이름.*기본정보/ })).toBeVisible();
  await expect(page.getByText(ACCOUNT_A_PROFILE.maskedName, { exact: true })).toHaveCount(0);
});

test('프로필 조회 실패는 관리 수치와 분리되고 다시 시도할 수 있다', async ({ page }) => {
  let profileAttempts = 0;
  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/v1/users/me') {
      profileAttempts += 1;
      if (profileAttempts <= 2) {
        await route.fulfill({ status: 503, json: { message: '프로필 조회 실패' } });
        return;
      }
      await route.fulfill({ json: ACCOUNT_B_PROFILE });
      return;
    }
    const body = myPageFixture(pathname);
    if (body === undefined) {
      await route.abort();
      return;
    }
    await route.fulfill({ json: body });
  });

  await page.goto('/dev/my-authenticated');

  await expect(page.getByRole('alert', { name: '프로필 정보 불러오기 실패' })).toBeVisible();
  await expect(page.getByRole('button', { name: '복용 중 처방 0개', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '프로필 다시 시도' }).click();
  await expect(page.getByRole('button', { name: /두 번째 계정 이름.*기본정보/ })).toBeVisible();
});

test('주체가 바뀌면 이전 이름을 지우고 늦은 이전 응답을 무시한다', async ({ page }) => {
  const staleRequests: Route[] = [];
  const nextPrincipalRequests: Route[] = [];
  let principalChanged = false;
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'profile-isolation-token');
    sessionStorage.setItem('poke.account-principal', 'account-a@example.com');
  });
  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/v1/users/me') {
      if (principalChanged) {
        nextPrincipalRequests.push(route);
        return;
      }
      if (staleRequests.length === 0) {
        staleRequests.push(route);
        return;
      }
      await route.fulfill({ json: ACCOUNT_A_PROFILE });
      return;
    }
    const body = myPageFixture(pathname);
    if (body === undefined) {
      await route.abort();
      return;
    }
    await route.fulfill({ json: body });
  });

  await page.goto('/dev/my-authenticated');
  await expect(page.getByRole('button', { name: /첫 계정 이름.*기본정보/ })).toBeVisible();
  principalChanged = true;
  await page.evaluate(() => window.dispatchEvent(new Event('poke:auth-session-expired')));

  await expect.poll(() => nextPrincipalRequests.length).toBeGreaterThan(0);
  await expect(page.getByRole('status', { name: '프로필 불러오는 중' })).toBeVisible();
  await expect(page.getByText(ACCOUNT_A_PROFILE.name, { exact: true })).toHaveCount(0);
  await Promise.all(nextPrincipalRequests.map((route) => route.fulfill({ json: ACCOUNT_B_PROFILE })));
  await expect(page.getByRole('button', { name: /두 번째 계정 이름.*기본정보/ })).toBeVisible();
  await Promise.all(staleRequests.map((route) => route.fulfill({ json: ACCOUNT_A_PROFILE })));
  await expect(page.getByText(ACCOUNT_A_PROFILE.name, { exact: true })).toHaveCount(0);
  await expect(page.getByText(ACCOUNT_B_PROFILE.name, { exact: true })).toBeVisible();
});

test('설정 API 시간은 마이페이지에서 HH:MM으로 보이고 저장 PATCH는 camelCase를 유지한다', async ({
  page,
}) => {
  const patchBodies: unknown[] = [];
  const response = {
    notifyMedication: false,
    notifySupplement: false,
    notifySchedule: false,
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

  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  await chooseMyTime(page, '아침', '08', '30');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  expect(patchBodies).toEqual([{
    morningMedicationTime: '08:30',
    lunchMedicationTime: '13:00',
    eveningMedicationTime: '19:00',
    bedtimeMedicationTime: '22:00',
  }]);
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
    notifySchedule: false,
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
    notifySchedule: false,
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
    notifySchedule: false,
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

test('기존 10분 단위가 아닌 진료 시간은 반올림하지 않고 지우거나 재선택한다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-09-08T03:00:00Z'));
  const patchBodies: unknown[] = [];
  await page.route('**/api/v1/user/follow-up-visits?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 47,
            user_id: 7,
            visit_date: '2026-09-21',
            visit_time: '15:17:00',
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
  await page.route('**/api/v1/user/follow-up-visits/47', async (route) => {
    const body = route.request().postDataJSON() as {
      visit_date: string;
      visit_time: string | null;
      hospital: string | null;
    };
    patchBodies.push(body);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 47,
        user_id: 7,
        visit_date: body.visit_date,
        visit_time: body.visit_time ? `${body.visit_time}:00` : null,
        hospital: body.hospital,
        created_at: '2026-09-02T10:00:00+09:00',
        updated_at: '2026-09-08T10:00:00+09:00',
      }),
    });
  });

  await page.goto('/dev/my-visits');
  await page.getByRole('button', { name: /9월 21일.*새봄병원.*15:17/ }).click();

  const visitSheet = page.getByRole('dialog', { name: '진료일정 수정' });
  await expect(
    visitSheet.getByRole('button', { name: '진료 시간 15:17' }),
  ).toBeVisible();
  await expect(visitSheet.getByText('진료 시간은 10분 단위로 선택해주세요.')).toBeVisible();
  await expect(visitSheet.getByRole('button', { name: '저장' })).toBeDisabled();

  await visitSheet.getByRole('button', { name: '진료 시간 15:17' }).click();
  const timeSheet = page.getByRole('dialog', { name: '시간 선택' });
  await expect(timeSheet.getByText('현재 저장된 15:17은 10분 단위가 아니에요.')).toBeVisible();
  await expect(timeSheet.getByLabel('분')).toHaveAttribute('aria-invalid', 'true');
  await expect(timeSheet.getByLabel('분')).toHaveAttribute('aria-describedby', /.+/);
  await timeSheet.getByRole('button', { name: '취소' }).click();
  await visitSheet.getByRole('button', { name: '시간 지우기' }).click();
  await expect(visitSheet.getByRole('button', { name: '저장' })).toBeEnabled();
  await visitSheet.getByRole('button', { name: '저장' }).click();

  expect(patchBodies).toEqual([
    {
      visit_date: '2026-09-21',
      visit_time: null,
      hospital: '새봄병원',
    },
  ]);

  const clearedVisit = page.getByRole('button', { name: /9월 21일.*새봄병원.*시간 미정/ });
  await clearedVisit.click();
  const reopenedVisitSheet = page.getByRole('dialog', { name: '진료일정 수정' });
  await reopenedVisitSheet.getByRole('button', { name: '진료 시간 시간 미정' }).click();
  const reopenedTimeSheet = page.getByRole('dialog', { name: '시간 선택' });
  await reopenedTimeSheet.getByLabel('시').click();
  await page.getByRole('option', { name: '15시', exact: true }).click();
  await reopenedTimeSheet.getByLabel('분').click();
  await page.getByRole('option', { name: '20분', exact: true }).click();
  await reopenedTimeSheet.getByRole('button', { name: '이 시간 적용' }).click();
  await reopenedVisitSheet.getByRole('button', { name: '저장' }).click();

  expect(patchBodies).toEqual([
    {
      visit_date: '2026-09-21',
      visit_time: null,
      hospital: '새봄병원',
    },
    {
      visit_date: '2026-09-21',
      visit_time: '15:20',
      hospital: '새봄병원',
    },
  ]);
});

test('마이페이지 일정 알림 토글은 notifySchedule만 PATCH한다', async ({ page }) => {
  const patchBodies: unknown[] = [];
  const response = {
    notifyMedication: false,
    notifySupplement: false,
    notifySchedule: true,
    notifyConsentedAt: '2026-09-02T10:00:00+09:00',
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
        body: JSON.stringify({ ...response, notifySchedule: false }),
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
  const scheduleSwitch = page.getByRole('switch', { name: '일정 알림' });
  await expect(scheduleSwitch).toBeChecked();
  await scheduleSwitch.click();

  await expect(scheduleSwitch).not.toBeChecked();
  expect(patchBodies).toEqual([{ notifySchedule: false }]);
});
