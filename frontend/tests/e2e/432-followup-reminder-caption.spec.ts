import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

const settings = {
  notifyMedication: false, notifySupplement: false, notifySchedule: false,
  notifyConsentedAt: '2026-09-01T00:00:00Z', morningMedicationTime: '08:00:00',
  lunchMedicationTime: '13:00:00', eveningMedicationTime: '18:00:00', bedtimeMedicationTime: '22:00:00',
};

test.beforeEach(async ({ page }) => {
  page.setDefaultTimeout(10000);
  page.setDefaultNavigationTimeout(60000);
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'fixture-only-token');
    sessionStorage.setItem('poke.account-principal', 'reminder-fixture@example.com');
    class StubNotification {
      static permission = 'granted';
      static async requestPermission() { return StubNotification.permission; }
    }
    Object.defineProperty(window, 'Notification', { configurable: true, value: StubNotification });
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
      register: async () => ({ pushManager: {
        getSubscription: async () => null,
        subscribe: async () => ({ toJSON: () => ({
          endpoint: 'https://push.example.test/reminder-fixture',
          keys: { p256dh: 'fixture-key', auth: 'fixture-auth' },
        }) }),
      } }),
      getRegistration: async () => null,
    } });
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/users/me', route => route.fulfill({ json: {
    name: '테스트', maskedName: '테*트', phoneNumber: null, birthDate: null, gender: null,
  } }));
  await page.route('**/api/v1/medications?*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/med/user-suppl-nutr?*', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100, nutrient_standard: null } }));
  await page.route('**/api/v1/user/follow-up-visits?*', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 100 } }));
  await page.route('**/api/v1/me/settings', route => route.fulfill({ json: settings }));
  await page.route('**/api/v1/alarms/push-subscriptions', route => route.fulfill({ json: { id: 1 } }));
});

for (const width of [390, 1280]) {
  test(`schedule caption stays under its label independently of medication time at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/my');
    const notifications = page.getByRole('region', { name: '알림', exact: true });
    const schedule = notifications.getByRole('switch', { name: '일정 알림', exact: true });
    await expect(schedule).not.toBeChecked();
    await expect(schedule).toHaveAccessibleDescription('전날 21:00 알림');
    const caption = notifications.getByText('전날 21:00 알림', { exact: true });
    await expect(caption).toHaveCount(1);
    await expect(notifications.getByRole('switch', { name: '복약 알림', exact: true })).not.toHaveAttribute('aria-describedby');
    await expect(notifications.getByRole('switch', { name: '영양제 알림', exact: true })).not.toHaveAttribute('aria-describedby');
    await expect(notifications.getByRole('button', { name: /알림 시간 설정/ })).toContainText('08:00 · 13:00 · 18:00 · 22:00');
    const labelBox = await notifications.locator('label').filter({ hasText: /^일정 알림$/ }).boundingBox();
    const captionBox = await caption.boundingBox();
    const switchBox = await schedule.boundingBox();
    expect(captionBox!.y).toBeGreaterThanOrEqual(labelBox!.y + labelBox!.height);
    expect(switchBox!.x).toBeGreaterThan(captionBox!.x + captionBox!.width);
    await notifications.screenshot({ path: testInfo.outputPath(`schedule-reminder-${width}.png`), animations: 'disabled' });
  });
}

test('schedule toggle retains pending lock and saves only schedule preference', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const writes: unknown[] = [];
  await page.route('**/api/v1/me/settings', async route => {
    if (route.request().method() !== 'PATCH') return route.fulfill({ json: settings });
    writes.push(route.request().postDataJSON());
    await gate;
    return route.fulfill({ json: { ...settings, notifySchedule: true } });
  });
  await page.goto('/my');
  const schedule = page.getByRole('switch', { name: '일정 알림', exact: true });
  await schedule.focus();
  await page.keyboard.press('Space');
  await expect(schedule).toBeChecked();
  await expect(schedule).toBeDisabled();
  await expect.poll(() => writes).toEqual([{ notifySchedule: true }]);
  release();
  await expect(schedule).toBeEnabled();
  await expect(schedule).toBeChecked();
  await expect(page.getByRole('switch', { name: '복약 알림', exact: true })).not.toBeChecked();
  await expect(page.getByRole('switch', { name: '영양제 알림', exact: true })).not.toBeChecked();
});

test('schedule toggle rolls back on a save error', async ({ page }) => {
  await page.route('**/api/v1/me/settings', route => route.request().method() === 'PATCH'
    ? route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '설정 저장 실패' } })
    : route.fulfill({ json: settings }));
  await page.goto('/my');
  const schedule = page.getByRole('switch', { name: '일정 알림', exact: true });
  await schedule.click();
  await expect(page.getByRole('dialog', { name: '알림 설정을 저장하지 못했어요' })).toContainText('설정 저장 실패');
  await expect(page.locator('[role="switch"][aria-label="일정 알림"]')).not.toBeChecked();
});

test('unsupported notifications keep the schedule switch disabled', async ({ page }) => {
  await page.addInitScript(() => { Reflect.deleteProperty(window, 'Notification'); });
  await page.goto('/my');
  await expect(page.getByRole('switch', { name: '일정 알림', exact: true })).toBeDisabled();
  await expect(page.getByText('전날 21:00 알림', { exact: true })).toBeVisible();
});

test('schedule permission consent can be dismissed without changing settings', async ({ page }) => {
  const writes: string[] = [];
  page.on('request', request => {
    if (request.method() === 'PATCH') writes.push(request.url());
  });
  await page.goto('/my');
  await page.evaluate(() => Object.defineProperty(Notification, 'permission', { configurable: true, value: 'default' }));
  await page.getByRole('switch', { name: '일정 알림', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '일정 알림을 보내드릴까요?', exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: '나중에', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('switch', { name: '일정 알림', exact: true })).not.toBeChecked();
  expect(writes).toEqual([]);
});
