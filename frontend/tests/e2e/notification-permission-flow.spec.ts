import { expect, test, type Page } from 'playwright/test';

type StubbedPermission = NotificationPermission | 'unsupported';

async function stubNotificationPermission(
  page: Page,
  permission: StubbedPermission,
  requestedPermission: NotificationPermission = 'granted',
) {
  await page.addInitScript(
    ({ initialPermission, nextPermission }) => {
      if (initialPermission === 'unsupported') {
        Reflect.deleteProperty(window, 'Notification');
        return;
      }

      class StubNotification {
        static permission = initialPermission;

        static async requestPermission() {
          StubNotification.permission = nextPermission;
          return nextPermission;
        }
      }

      Object.defineProperty(window, 'Notification', {
        configurable: true,
        value: StubNotification,
      });
    },
    { initialPermission: permission, nextPermission: requestedPermission },
  );
}

async function stubPushManager(page: Page) {
  await page.addInitScript(() => {
    const subscription = {
      endpoint: 'https://push.example.test/device-116',
      expirationTime: null,
      keys: { p256dh: 'p256dh-test-key', auth: 'auth-test-key' },
    };
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        register: async () => ({
          pushManager: {
            getSubscription: async () => null,
            subscribe: async () => ({ toJSON: () => subscription }),
          },
        }),
      },
    });
  });
}

test('알림 설정은 복약·영양제 모두 꺼진 서버 기본값으로 시작한다', async ({ page }) => {
  await stubNotificationPermission(page, 'default');
  await page.goto('/dev/my-authenticated');

  await expect(page.locator('[role="switch"][aria-label="복약 알림"]')).not.toBeChecked();
  await expect(page.locator('[role="switch"][aria-label="영양제 알림"]')).not.toBeChecked();
});

test('마이페이지에서 default 권한의 토글을 켜면 브라우저 요청보다 사전 팝업을 먼저 연다', async ({
  page,
}) => {
  await stubNotificationPermission(page, 'default');
  await page.goto('/dev/my-authenticated');

  await page.getByRole('switch', { name: '복약 알림' }).click();

  const dialog = page.getByRole('dialog', { name: '복약 시간에 알림을 보내드릴까요?' });
  await expect(dialog).toBeVisible();
  await expect(page.locator('[role="switch"][aria-label="복약 알림"]')).not.toBeChecked();
  await expect(dialog.getByRole('button', { name: '나중에' })).toBeVisible();
  await expect(dialog.getByRole('button', { name: '좋아요' })).toBeVisible();
});

test('마이페이지에서 denied 권한의 토글은 켜지지 않고 브라우저 설정 안내를 보여준다', async ({
  page,
}) => {
  await stubNotificationPermission(page, 'denied');
  await page.goto('/dev/my-authenticated');

  await page.getByRole('switch', { name: '영양제 알림' }).click();

  await expect(page.locator('[role="switch"][aria-label="영양제 알림"]')).not.toBeChecked();
  const dialog = page.getByRole('dialog', { name: '알림이 차단되어 있어요' });
  await expect(dialog).toContainText('주소창 왼쪽 자물쇠(또는 ⓘ)');
});

test('마이페이지 허용에서는 누른 토글만 켜고 기존 알람 구독 API를 호출한다', async ({ page }) => {
  await stubNotificationPermission(page, 'default', 'granted');
  await stubPushManager(page);
  const subscriptions: Array<{ method: string; body: unknown }> = [];
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    subscriptions.push({
      method: route.request().method(),
      body: route.request().postDataJSON(),
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1 }),
    });
  });
  await page.goto('/dev/my-authenticated');

  await page.getByRole('switch', { name: '복약 알림' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '좋아요' }).click();

  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeChecked();
  await expect(page.getByRole('switch', { name: '영양제 알림' })).not.toBeChecked();
  expect(subscriptions).toEqual([
    {
      method: 'PUT',
      body: {
        endpoint: 'https://push.example.test/device-116',
        p256dh_key: 'p256dh-test-key',
        auth_key: 'auth-test-key',
        platform: 'web',
        user_agent: expect.any(String),
      },
    },
  ]);

  await page.getByRole('switch', { name: '복약 알림' }).click();
  await expect(page.getByRole('switch', { name: '복약 알림' })).not.toBeChecked();
  expect(subscriptions).toHaveLength(1);
});

test('알림 미지원 브라우저에서는 두 토글을 비활성화하고 안내한다', async ({ page }) => {
  await stubNotificationPermission(page, 'unsupported');
  await page.goto('/dev/my-authenticated');

  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeDisabled();
  await expect(page.getByRole('switch', { name: '영양제 알림' })).toBeDisabled();
  await expect(page.getByText('이 브라우저에서는 알림을 지원하지 않아요')).toBeVisible();
});

test('iOS Safari 일반 탭은 알림 미지원으로 처리하고 화면이 깨지지 않는다', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1',
    });
    Object.defineProperty(navigator, 'standalone', { configurable: true, value: false });
  });
  await stubNotificationPermission(page, 'default');
  await page.goto('/dev/my-authenticated');

  await expect(page.getByRole('heading', { name: '마이페이지' })).toBeVisible();
  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeDisabled();
  await expect(page.getByText('이 브라우저에서는 알림을 지원하지 않아요')).toBeVisible();
});

test('서비스워커는 push 표시와 알림 클릭 이동을 처리한다', async ({ request }) => {
  const response = await request.get('/sw.js');
  expect(response.ok()).toBe(true);
  const source = await response.text();
  expect(source).toContain("addEventListener('push'");
  expect(source).toContain('showNotification');
  expect(source).toContain("addEventListener('notificationclick'");
});

test('복약시간 저장 성공 뒤 방금 정한 네 시각으로 최초 권한 사전 팝업을 연다', async ({ page }) => {
  await stubNotificationPermission(page, 'default');
  await page.goto('/dev/medication-schedule');
  await page.getByRole('button', { name: '시작 아침' }).click();
  await page.getByRole('button', { name: '저장하고 계속' }).click();

  await expect(page).toHaveURL(/\/dev\/medication-schedule$/);
  const dialog = page.getByRole('dialog', { name: '복약 시간에 알림을 보내드릴까요?' });
  await expect(dialog).toContainText('아침 08:00 · 점심 13:00 · 저녁 19:00 · 취침 22:00');
});

test('복약시간 저장이 실패하면 권한 팝업을 열지 않는다', async ({ page }) => {
  await stubNotificationPermission(page, 'default');
  await page.goto('/dev/medication-schedule-save-error');
  await page.getByRole('button', { name: '시작 아침' }).click();
  await page.getByRole('button', { name: '저장하고 계속' }).click();

  await expect(page.getByRole('dialog', { name: '복약 시간을 저장하지 못했어요' })).toBeVisible();
  await expect(
    page.getByRole('dialog', { name: '복약 시간에 알림을 보내드릴까요?' }),
  ).toHaveCount(0);
});

test('복약시간 사전 팝업에서 나중에를 고르면 브라우저 권한을 요청하지 않고 홈으로 간다', async ({
  page,
}) => {
  await stubNotificationPermission(page, 'default');
  await page.goto('/dev/medication-schedule');
  await page.getByRole('button', { name: '시작 아침' }).click();
  await page.getByRole('button', { name: '저장하고 계속' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '나중에' }).click();

  await expect(page).toHaveURL(/\/home$/);
  expect(await page.evaluate(() => Notification.permission)).toBe('default');
});

test('나중에를 기록한 뒤 복약시간 설정에 다시 들어가면 권한 팝업을 반복하지 않는다', async ({ page }) => {
  await stubNotificationPermission(page, 'default');
  await page.goto('/dev/medication-schedule');
  await page.getByRole('button', { name: '시작 아침' }).click();
  await page.getByRole('button', { name: '저장하고 계속' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '나중에' }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.evaluate(() => {
    window.history.pushState({}, '', '/dev/medication-schedule');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await page.getByRole('button', { name: '시작 아침' }).click();
  await page.getByRole('button', { name: '저장하고 계속' }).click();

  await expect(page).toHaveURL(/\/home$/);
  await expect(
    page.getByRole('dialog', { name: '복약 시간에 알림을 보내드릴까요?' }),
  ).toHaveCount(0);
  expect(await page.evaluate(() => Notification.permission)).toBe('default');
});

test('복약시간 최초 허용은 복약·영양제 토글을 함께 켠다', async ({ page }) => {
  await stubNotificationPermission(page, 'default', 'granted');
  await stubPushManager(page);
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"id":1}' });
  });
  await page.goto('/dev/medication-schedule');
  await page.getByRole('button', { name: '시작 아침' }).click();
  await page.getByRole('button', { name: '저장하고 계속' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '좋아요' }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.evaluate(() => {
    window.history.pushState({}, '', '/dev/my-authenticated');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeChecked();
  await expect(page.getByRole('switch', { name: '영양제 알림' })).toBeChecked();
});
