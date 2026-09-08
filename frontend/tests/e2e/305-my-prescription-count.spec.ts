import { expect, test, type Page } from 'playwright/test';
import type { MedicationOverview } from '../../src/entities/medication/types';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.setTimeout(45_000);
test.beforeEach(() => test.skip(!IS_REAL_API, REAL_API_ONLY_REASON));

function prescription(id: number, date: string, finished: boolean, drugCount = 4): MedicationOverview {
  return {
    recordId: id, alias: `테스트 처방 ${id}`, documentImageUrl: '',
    start: { date, slot: 'morning' }, endDate: finished ? date : '2026-09-11',
    daysRemaining: finished ? 0 : 4, isFinished: finished,
    mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:00' },
    medications: Array.from({ length: drugCount }, (_, i) => ({
      medicationId: id * 10 + i, name: `테스트 약 ${i}`, dose: '1정', days: 7,
      daysRemaining: finished ? 0 : 4, slots: ['morning'], asNeeded: false,
    })),
  };
}

async function openMy(page: Page, prescriptions: MedicationOverview[], fail = false, now = '2026-09-08T03:00:00Z') {
  const requestedRanges: string[] = [];
  await page.clock.setFixedTime(new Date(now));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'prescription-count-test-token');
    sessionStorage.setItem('poke.account-principal', 'prescription-count@example.com');
  });
  // Only intercept HTTP API boundaries, never Vite's /src/shared/api modules.
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    let body: unknown;
    if (url.pathname === '/api/v1/medications') {
      requestedRanges.push(url.search);
      if (fail) {
        await route.fulfill({ status: 500, json: { message: '테스트 조회 오류' } });
        return;
      }
      const from = url.searchParams.get('from') ?? '2026-03-08';
      const to = url.searchParams.get('to') ?? '2026-09-08';
      body = prescriptions.filter((item) => item.start.date >= from && item.start.date <= to);
    } else if (url.pathname === '/api/v1/med/user-suppl-nutr' || url.pathname === '/api/v1/user/follow-up-visits') {
      body = { items: [], total: 0, offset: 0, limit: 100 };
    } else if (url.pathname === '/api/v1/me/settings') {
      body = {
        notifyMedication: false, notifySupplement: false, notifySchedule: false,
        notifyConsentedAt: null, morningMedicationTime: '08:00', lunchMedicationTime: '13:00',
        eveningMedicationTime: '19:00', bedtimeMedicationTime: '22:00',
      };
    } else { await route.abort(); return; }
    await route.fulfill({ json: body });
  });
  await page.goto('/my');
  await expect(page.getByRole('heading', { name: '마이페이지' })).toBeVisible();
  return requestedRanges;
}

test('My counts ongoing prescriptions rather than drugs or completed records and opens the six-month list', async ({ page }, testInfo) => {
  const ranges = await openMy(page, [
    ...Array.from({ length: 7 }, (_, i) => prescription(i + 1, '2026-09-05', false, i === 0 ? 6 : 4)),
    prescription(8, '2026-09-02', true),
    prescription(9, '2025-02-19', true),
    prescription(10, '2026-09-05', false, 0),
  ]);
  const recordButton = page.getByRole('button', { name: '복용 중 처방 7개', exact: true });
  await expect(recordButton).toBeVisible();
  expect(ranges[0]).toBe('?from=2024-09-08&to=2026-09-08');
  await expect(page.getByRole('button', { name: /^복용약/ })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('my-prescription-count.png'), fullPage: true });
  await recordButton.click();
  await expect(page).toHaveURL(/\/medications$/);
  await expect(page.getByText('테스트 처방 8', { exact: true })).toBeVisible();
  await expect(page.getByText('테스트 처방 9', { exact: true })).toHaveCount(0);
  expect(ranges.at(-1)).toBe('');
});

test('an ongoing prescription older than six months is still counted', async ({ page }) => {
  const ongoing = prescription(1, '2026-01-01', false);
  ongoing.endDate = '2026-12-31';
  ongoing.medications.forEach((medication) => { medication.days = 365; });
  await openMy(page, [ongoing, prescription(2, '2026-09-02', true)]);
  await expect(page.getByRole('button', { name: '복용 중 처방 1개', exact: true })).toBeVisible();
});

test('an empty prescription list displays zero records', async ({ page }) => {
  await openMy(page, []);
  await expect(page.getByRole('button', { name: '복용 중 처방 0개', exact: true })).toBeVisible();
});

test('a failed prescription request is not misrepresented as zero records', async ({ page }) => {
  await openMy(page, [], true);
  await expect(page.getByRole('button', { name: '복용 중 처방 확인 불가', exact: true })).toBeVisible();
  await expect(page.getByRole('alert', { name: '관리 정보 불러오기 실패' })).toBeVisible();
});

for (const [timezoneId, now] of [
  ['UTC', '2026-09-07T16:00:00Z'],
  ['Pacific/Kiritimati', '2026-09-08T12:00:00Z'],
] as const) {
  test.describe(timezoneId, () => {
    test.use({ timezoneId });
    test('count range uses server Korea date at a timezone boundary', async ({ page }) => {
      const ranges = await openMy(page, [prescription(1, '2026-09-05', false)], false, now);
      await expect(page.getByRole('button', { name: '복용 중 처방 1개', exact: true })).toBeVisible();
      expect(ranges[0]).toBe('?from=2024-09-08&to=2026-09-08');
    });
  });
}
