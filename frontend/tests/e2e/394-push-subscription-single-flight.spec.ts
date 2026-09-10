/**
 * #394 — 알림 토글을 동시에 켜도 Push 구독은 하나만 만든다.
 *
 * 실제 Chrome 으로 재현한 결과: `registerPushNotifications()` 를 동시에 3번 부르면
 * 세 호출이 모두 `getSubscription()` 에서 `null` 을 보고 각자 `subscribe()` 를 실행하고,
 * FCM 이 호출마다 새 endpoint 를 발급한다(순차 3회는 1개, 동시 3회는 3개).
 * 구독이 늘어난 만큼 같은 알림이 중복 발송된다.
 *
 * 그래서 여기서는 **`subscribe()` 호출 횟수**를 직접 센다. PUT 횟수만 보면
 * 구독이 여러 개 만들어진 뒤 마지막 것만 저장되는 경우를 놓친다.
 *
 * `subscribe()` 에 지연을 넣는 것이 핵심이다. 지연이 없으면 첫 호출이 즉시 끝나
 * 두 번째 호출이 재사용 경로를 타므로 경합이 재현되지 않는다.
 */
import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

interface PushProbe {
  subscribeCalls: number;
  endpoints: string[];
}

type ProbedWindow = typeof window & { __pushProbe?: PushProbe };

/** 권한은 이미 허용된 상태로 둔다. 이 스펙은 권한 흐름을 보지 않는다. */
async function stubGrantedPermission(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: class {
        static permission: NotificationPermission = 'granted';
        static async requestPermission(): Promise<NotificationPermission> {
          return 'granted';
        }
      },
    });
  });
}

/** subscribe 마다 새 endpoint 를 주는 Push 서비스. 실제 FCM 의 동작이다. */
async function stubRacingPushManager(page: Page, subscribeDelayMs: number) {
  await page.addInitScript((delayMs) => {
    const probed = window as ProbedWindow;
    const probe: PushProbe = { subscribeCalls: 0, endpoints: [] };
    probed.__pushProbe = probe;

    let current: { toJSON: () => unknown } | null = null;
    const registration = {
      pushManager: {
        getSubscription: async () => current,
        subscribe: async () => {
          probe.subscribeCalls += 1;
          const endpoint = `https://push.example.test/device-${probe.subscribeCalls}`;
          // FCM 왕복 지연. 이 사이에 다른 토글이 들어오면 경합이 생긴다.
          await new Promise((resolve) => setTimeout(resolve, delayMs));
          probe.endpoints.push(endpoint);
          current = {
            toJSON: () => ({
              endpoint,
              expirationTime: null,
              keys: { p256dh: 'p256dh-test-key', auth: 'auth-test-key' },
            }),
          };
          return current;
        },
      },
    };

    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { register: async () => registration, ready: Promise.resolve(registration) },
    });
  }, subscribeDelayMs);
}

/** PUT 본문을 모아 둔다. 라우트를 가로채므로 실제 서버로는 나가지 않는다. */
async function collectSubscriptionPuts(page: Page) {
  const puts: Array<Record<string, unknown>> = [];
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    if (route.request().method() === 'PUT') {
      puts.push(route.request().postDataJSON());
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1 }),
    });
  });
  return puts;
}

test('세 알림 토글을 동시에 켜도 Push 구독은 한 번만 만든다', async ({ page }) => {
  await stubGrantedPermission(page);
  await stubRacingPushManager(page, 120);
  const puts = await collectSubscriptionPuts(page);
  await page.goto('/dev/my-authenticated');

  // 사람이 세 토글을 연달아 누르는 상황. `subscribe()` 지연(120ms) 안에 세 클릭을
  // 모두 넣어 등록이 겹치게 한다. click() 은 이벤트를 보낸 뒤 바로 반환하므로
  // 앞의 등록이 끝나기를 기다리지 않는다.
  //
  // 세 클릭을 같은 틱에 몰면(Promise.all) 낙관적 갱신 리렌더 사이에 클릭이 유실되어
  // 토글이 켜지지 않는다. 간격을 조금 두는 편이 실제 사용에도 가깝다.
  await page.getByRole('switch', { name: '복약 알림' }).click();
  await page.waitForTimeout(20);
  await page.getByRole('switch', { name: '영양제 알림' }).click();
  await page.waitForTimeout(20);
  await page.getByRole('switch', { name: '일정 알림' }).click();

  await expect.poll(() => puts.length).toBe(1);
  // 뒤늦게 오는 구독이 없는지 확인한다. subscribe 지연보다 넉넉히 기다린다.
  await page.waitForTimeout(400);

  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeChecked();
  await expect(page.getByRole('switch', { name: '영양제 알림' })).toBeChecked();
  await expect(page.getByRole('switch', { name: '일정 알림' })).toBeChecked();

  const probe = await page.evaluate(() => (window as ProbedWindow).__pushProbe);
  expect(probe?.subscribeCalls).toBe(1);
  expect(probe?.endpoints).toEqual(['https://push.example.test/device-1']);
  expect(puts).toEqual([
    {
      endpoint: 'https://push.example.test/device-1',
      p256dh_key: 'p256dh-test-key',
      auth_key: 'auth-test-key',
      platform: 'web',
      user_agent: expect.any(String),
    },
  ]);
});

test('등록이 끝난 뒤 다시 켜면 기존 브라우저 구독을 재사용한다', async ({ page }) => {
  await stubGrantedPermission(page);
  await stubRacingPushManager(page, 0);
  const puts = await collectSubscriptionPuts(page);
  await page.goto('/dev/my-authenticated');

  await page.getByRole('switch', { name: '복약 알림' }).click();
  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeChecked();
  await page.getByRole('switch', { name: '영양제 알림' }).click();
  await expect(page.getByRole('switch', { name: '영양제 알림' })).toBeChecked();

  // 등록 작업은 끝났으므로 두 번째 호출은 새로 실행된다. 다만 브라우저 구독을
  // 재사용하므로 subscribe 는 늘지 않고, 같은 endpoint 로 갱신 PUT 만 한 번 더 간다.
  const probe = await page.evaluate(() => (window as ProbedWindow).__pushProbe);
  expect(probe?.subscribeCalls).toBe(1);
  expect(puts).toHaveLength(2);
  expect(new Set(puts.map((body) => body.endpoint))).toEqual(
    new Set(['https://push.example.test/device-1']),
  );
});

test('서비스워커가 활성화되기 전에는 구독하지 않고 활성화를 기다린다', async ({ page }) => {
  await stubGrantedPermission(page);
  // `register()` 는 활성화 전에 resolve 한다. 그 registration 으로 곧바로 구독하면
  // 서비스워커를 처음 설치하는 브라우저에서 AbortError 로 실패한다(#394 실측).
  await page.addInitScript(() => {
    const failing = {
      pushManager: {
        getSubscription: async () => {
          throw new Error('no active Service Worker');
        },
        subscribe: async () => {
          throw new Error('Subscription failed - no active Service Worker');
        },
      },
    };
    const activated = {
      pushManager: {
        getSubscription: async () => null,
        subscribe: async () => ({
          toJSON: () => ({
            endpoint: 'https://push.example.test/device-activated',
            expirationTime: null,
            keys: { p256dh: 'p256dh-test-key', auth: 'auth-test-key' },
          }),
        }),
      },
    };
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        register: async () => failing,
        ready: new Promise((resolve) => setTimeout(() => resolve(activated), 60)),
      },
    });
  });
  const puts = await collectSubscriptionPuts(page);
  await page.goto('/dev/my-authenticated');

  await page.getByRole('switch', { name: '복약 알림' }).click();

  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeChecked();
  await expect(page.getByRole('dialog', { name: '알림 설정을 저장하지 못했어요' })).toHaveCount(0);
  expect(puts.map((body) => body.endpoint)).toEqual([
    'https://push.example.test/device-activated',
  ]);
});
