import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.setTimeout(30_000);

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8+QAAAABJRU5ErkJggg==',
  'base64',
);

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

async function stubPushManager(page: Page, alreadyRegistered = false) {
  await page.addInitScript(({ hasExistingSubscription }) => {
    const subscription = {
      endpoint: 'https://push.example.test/feature-252-device',
      expirationTime: null,
      keys: { p256dh: 'feature-252-p256dh', auth: 'feature-252-auth' },
    };
    const existing = hasExistingSubscription ? { toJSON: () => subscription } : null;
    const pushState = window as Window & { __feature252PushSubscribeCalls: number };
    Object.defineProperty(pushState, '__feature252PushSubscribeCalls', {
      configurable: true,
      writable: true,
      value: 0,
    });
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: {
        register: async () => ({
          pushManager: {
            getSubscription: async () => existing,
            subscribe: async () => {
              pushState.__feature252PushSubscribeCalls += 1;
              return { toJSON: () => subscription };
            },
          },
        }),
      },
    });
  }, { hasExistingSubscription: alreadyRegistered });
}

async function enterRegistrationAlarmStep(page: Page, alias = '알람 권한 처방') {
  await page.goto('/dev/ocr-review');
  await page.getByLabel('복약 별칭').fill(alias);
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '확인 후 저장' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '시작 점심약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
}

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.clock.setFixedTime(new Date('2026-09-03T12:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-252-medication-token');
    sessionStorage.setItem('poke.account-principal', 'feature-252-medication@example.com');
    if (sessionStorage.getItem('feature-252-storage-cleaned') === '1') return;
    for (const key of Object.keys(localStorage)) {
      if (
        key.startsWith('rxvita.medication-notes:') ||
        key.startsWith('rxvita.medication-aliases:') ||
        key.startsWith('rxvita.notify-settings:')
      ) {
        localStorage.removeItem(key);
      }
    }
    sessionStorage.setItem('feature-252-storage-cleaned', '1');
  });
});

test('약봉투 등록은 OCR·별칭·복용 시간·첫 복용·알람의 5단계로 이어진다', async ({ page }) => {
  await page.goto('/dev/ocr-review');

  await expect(page.getByText('2 / 5', { exact: true })).toBeVisible();
  await expect(
    page.getByText('사진에서 읽은 내용이에요. 실제 약봉투와 다르면 고쳐주세요.'),
  ).toBeVisible();
  await expect(page.getByLabel('복약 별칭')).toBeVisible();
  await page.getByLabel('복약 별칭').fill('감기약');

  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '확인 후 저장' }).click();

  await expect(page).toHaveURL(/\/medication-schedule\?recordId=12&ocrJobId=b_mock_9f21/);
  await expect(page.getByText('3 / 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '약마다 먹는 시간을 확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '확인', exact: true }).click();

  await expect(page.getByText('4 / 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '처음 약을 언제 드셨나요?' })).toBeVisible();
  await expect(page.getByText('이렇게 기록해요', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '시작 점심약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();

  await expect(page.getByText('5 / 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '알람 시간을 확인해주세요' })).toBeVisible();
  await expect(page.getByText('사용 안 함', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
});

test('선택한 약봉투는 업로드 뒤 OCR 진행률과 결과 검토로 이어진다', async ({ page }) => {
  await page.goto('/dev/document-upload');
  await expect(page.getByText('약국에서 받은 봉투 앞면이면 돼요.')).toBeVisible();
  await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({
    name: 'feature-252-envelope.png',
    mimeType: 'image/png',
    buffer: ONE_PIXEL_PNG,
  });
  await expect(page.getByRole('img', { name: '선택한 약봉투 미리보기' })).toBeVisible();
  await expect(page.getByText('feature-252-envelope.png')).toBeVisible();
  await page.getByRole('button', { name: '등록하기' }).click();

  await expect(page).toHaveURL('/ocr-review');
  await expect(page.getByRole('heading', { name: '약봉투를 읽고 있어요' })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: '약봉투 판독 진행률' })).toBeVisible();
  await expect(page.getByRole('status', { name: '약봉투 판독 단계' })).toContainText('/ 3 단계');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible({ timeout: 10_000 });
});

test('5단계 알람은 전체 알림과 시간 행을 편집하고 저장한다', async ({ page }) => {
  await stubNotificationPermission(page, 'default', 'granted');
  await stubPushManager(page);
  const pushPayloads: unknown[] = [];
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    pushPayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1 }),
    });
  });
  await enterRegistrationAlarmStep(page, '알람 저장 처방');

  const medicationNotifications = page.getByRole('switch', { name: '복약 알림' });
  await expect(medicationNotifications).toBeVisible();
  await medicationNotifications.click();
  const permissionDialog = page.getByRole('dialog', { name: '복약 시간에 알림을 보내드릴까요?' });
  await expect(permissionDialog).toBeVisible();
  await expect(page.locator('[role="switch"][aria-label="복약 알림"]')).toHaveAttribute(
    'aria-checked',
    'false',
  );
  await permissionDialog.getByRole('button', { name: '좋아요' }).click();
  await expect(medicationNotifications).toBeChecked();
  expect(pushPayloads).toHaveLength(1);

  const morningAlarm = page.getByRole('button', { name: '아침약 알람 시간' });
  await morningAlarm.click();
  const timeDialog = page.getByRole('dialog');
  await timeDialog.getByLabel('시').click();
  await page.getByRole('option', { name: '07시' }).click();
  await timeDialog.getByLabel('분').click();
  await page.getByRole('option', { name: '30분' }).click();
  await timeDialog.getByRole('button', { name: '이 시간 적용' }).click();
  await expect(morningAlarm).toContainText('07:30');

  await page.getByRole('button', { name: '등록 완료', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  await expect(page.getByText(/알림 07:30/)).toBeVisible();
  await page.goto('/dev/my-authenticated');
  await page.getByRole('button', { name: '알림 시간 설정' }).click();
  const settingsSheet = page.getByRole('dialog', { name: '알림 시간' });
  await expect(settingsSheet.getByLabel('아침 시')).toContainText('07');
  await expect(settingsSheet.getByLabel('아침 분')).toContainText('30');
});

test('등록 5단계는 default 권한을 허용한 뒤에만 알림을 켜고 구독을 등록한다', async ({ page }) => {
  await stubNotificationPermission(page, 'default', 'granted');
  await stubPushManager(page);
  const pushPayloads: unknown[] = [];
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    pushPayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1 }),
    });
  });

  await enterRegistrationAlarmStep(page);
  const medicationNotifications = page.getByRole('switch', { name: '복약 알림' });
  await medicationNotifications.click();

  const permissionDialog = page.getByRole('dialog', { name: '복약 시간에 알림을 보내드릴까요?' });
  await expect(permissionDialog).toBeVisible();
  await expect(page.locator('[role="switch"][aria-label="복약 알림"]')).toHaveAttribute(
    'aria-checked',
    'false',
  );
  await permissionDialog.getByRole('button', { name: '좋아요' }).click();

  await expect(medicationNotifications).toBeChecked();
  expect(pushPayloads).toEqual([
    {
      endpoint: 'https://push.example.test/feature-252-device',
      p256dh_key: 'feature-252-p256dh',
      auth_key: 'feature-252-auth',
      platform: 'web',
      user_agent: expect.any(String),
    },
  ]);
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
});

test('등록 5단계는 denied 권한에서 알림을 켜지 않고 구독도 등록하지 않는다', async ({ page }) => {
  await stubNotificationPermission(page, 'denied');
  await stubPushManager(page);
  const pushPayloads: unknown[] = [];
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    pushPayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1 }),
    });
  });

  await enterRegistrationAlarmStep(page);
  const medicationNotifications = page.getByRole('switch', { name: '복약 알림' });
  await medicationNotifications.click();

  await expect(medicationNotifications).not.toBeChecked();
  await expect(page.getByRole('alert')).toContainText('알림 권한이 차단되어 있어요');
  expect(pushPayloads).toHaveLength(0);
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  await page.goto('/dev/my-authenticated');
  await expect(page.getByRole('switch', { name: '복약 알림' })).not.toBeChecked();
});

test('등록 5단계는 구독 등록 실패 뒤 알림을 켠 상태로 저장하지 않는다', async ({ page }) => {
  await stubNotificationPermission(page, 'granted');
  await stubPushManager(page);
  const pushPayloads: unknown[] = [];
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    pushPayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'push_unavailable', message: '구독 등록에 실패했어요.' }),
    });
  });

  await enterRegistrationAlarmStep(page);
  const medicationNotifications = page.getByRole('switch', { name: '복약 알림' });
  await medicationNotifications.click();

  await expect(medicationNotifications).not.toBeChecked();
  await expect(page.getByRole('alert')).toContainText('구독 등록에 실패했어요.');
  expect(pushPayloads).toHaveLength(1);
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  await page.goto('/dev/my-authenticated');
  await expect(page.getByRole('switch', { name: '복약 알림' })).not.toBeChecked();
});

test('등록 5단계는 granted 기존 구독을 재사용하고 중복 subscribe하지 않는다', async ({ page }) => {
  await stubNotificationPermission(page, 'granted');
  await stubPushManager(page, true);
  const pushPayloads: unknown[] = [];
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    pushPayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1 }),
    });
  });

  await enterRegistrationAlarmStep(page);
  const medicationNotifications = page.getByRole('switch', { name: '복약 알림' });
  await medicationNotifications.click();

  await expect(medicationNotifications).toBeChecked();
  expect(pushPayloads).toHaveLength(1);
  expect(await page.evaluate(() => {
    const state = window as Window & { __feature252PushSubscribeCalls: number };
    return state.__feature252PushSubscribeCalls;
  })).toBe(0);
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  expect(pushPayloads).toHaveLength(1);
});

test('등록 5단계는 푸시 등록이 끝날 때까지 완료를 막고 일관된 알림 상태를 저장한다', async ({
  page,
}) => {
  await stubNotificationPermission(page, 'granted');
  await stubPushManager(page);
  const pushPayloads: unknown[] = [];
  let releasePushRegistration!: () => void;
  const pushRegistrationSettled = new Promise<void>((resolve) => {
    releasePushRegistration = resolve;
  });
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    pushPayloads.push(route.request().postDataJSON());
    await pushRegistrationSettled;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 1 }),
    });
  });

  await enterRegistrationAlarmStep(page);
  const medicationNotifications = page.getByRole('switch', { name: '복약 알림' });
  await medicationNotifications.click();
  const completionButton = page.getByRole('button', { name: '등록 완료', exact: true });

  await expect(completionButton).toBeDisabled();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toHaveCount(0);
  expect(pushPayloads).toHaveLength(1);
  await completionButton.evaluate((button) => {
    // disabled 속성을 우회한 프로그램적 click도 pending guard에서 멈춰야 합니다.
    button.removeAttribute('disabled');
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toHaveCount(0);
  await expect(page).toHaveURL(/\/medication-schedule\?/);

  releasePushRegistration();
  await expect(medicationNotifications).toBeChecked();
  await expect(completionButton).toBeEnabled();
  await completionButton.click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  await expect(page.getByText(/알림 08:00/)).toBeVisible();
  await page.goto('/dev/my-authenticated');
  await expect(page.getByRole('switch', { name: '복약 알림' })).toBeChecked();
});

test('OCR 낮은 확신 약은 확인 필요 상태에서 편집할 수 있다', async ({ page }) => {
  await page.goto('/dev/ocr-review');

  await expect(page.getByText('1곳만 확인해주세요')).toBeVisible();
  await expect(page.getByText('확인 필요', { exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: /리바록사반 10mg/ }).click();
  const editDialog = page.getByRole('dialog');
  await editDialog.getByLabel('약품명').fill('리바록사반 확인');
  await editDialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('button', { name: /리바록사반 확인/ })).toBeVisible();
});

test('복약 목록은 활성 회차를 편집하고 완료 회차를 읽기 전용으로 연다', async ({ page }) => {
  await page.goto('/medications');

  const activeCard = page.getByRole('button', { name: /2026년 8월 22일 처방/ });
  await expect(activeCard).toContainText('셀레콕시브 200mg');
  await expect(activeCard).toContainText('아침 08:00');
  await activeCard.click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: '처방 편집' })).toBeVisible();
  await expect(page.getByLabel('복약 별칭')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: '닫기' }).click();

  await page.getByRole('button', { name: /2026년 8월 24일 처방/ }).click();
  const completedDialog = page.getByRole('dialog');
  await expect(completedDialog.getByRole('heading', { name: '완료된 처방' })).toBeVisible();
  await expect(completedDialog).toContainText('완료된 처방은 내용만 확인할 수 있어요.');
  await expect(completedDialog.getByText('지난 처방', { exact: true })).toBeVisible();
  await expect(completedDialog.getByText('2026년 8월 24일 ~ 28일', { exact: true })).toBeVisible();
  await expect(completedDialog.getByText(/아목시실린 500mg/)).toBeVisible();
  await expect(completedDialog.getByText(/아침약 08:00/)).toBeVisible();
  await expect(completedDialog.getByLabel('복약 별칭')).toHaveCount(0);
  await expect(completedDialog.getByRole('button', { name: /아목시실린 아침약/ })).toHaveCount(0);
});

test('복약 삭제 선택 모드는 고정 안내와 비활성 위험 버튼을 먼저 보여준다', async ({ page }) => {
  await page.goto('/medications');
  await page.getByRole('button', { name: '삭제', exact: true }).click();

  await expect(page.getByRole('heading', { name: '삭제할 처방을 선택하세요' })).toBeVisible();
  const deleteButton = page.getByRole('button', { name: '선택한 처방 삭제' });
  await expect(deleteButton).toBeDisabled();
  await expect(deleteButton).toHaveClass(/bg-muted-bg/);

  await page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ }).check();
  await expect(deleteButton).toBeEnabled();
  await expect(deleteButton).toHaveClass(/bg-danger/);
});

test('등록 별칭과 회차 편집 별칭은 새로고침 뒤에도 메모에서 사용한다', async ({ page }) => {
  await page.goto('/dev/ocr-review');
  await page.getByLabel('복약 별칭').fill('OCR 등록 별칭');
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '확인 후 저장' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '시작 아침약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();

  await page.goto('/medications');
  await expect(page.getByText('OCR 등록 별칭', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('OCR 등록 별칭', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: /2026년 8월 22일 처방/ }).click();
  const episodeDialog = page.getByRole('dialog');
  await episodeDialog.getByLabel('복약 별칭').fill('회차 편집 별칭');
  await episodeDialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByText('처방을 저장했어요.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('회차 편집 별칭', { exact: true })).toBeVisible();

  await page.goto('/medications/notes/new');
  await expect(page.getByLabel('처방').locator('option[value="12"]')).toContainText('회차 편집 별칭');
  await page.getByLabel('처방').selectOption('12');
  await expect(page.getByLabel('약').locator('option[value="301"]')).toContainText('셀레콕시브 200mg');
  await page.getByLabel('약').selectOption('301');
  await page.getByLabel('복용 일시').fill('2026-09-03T15:20');
  await page.getByLabel('복용 후 느낀 점').fill('별칭을 포함한 메모');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByText('회차 편집 별칭', { exact: true })).toBeVisible();
});

test('복약 메모는 SessionContext principal별로 격리된다', async ({ page }) => {
  await page.goto('/medications/notes/new');
  await page.getByLabel('처방').selectOption('12');
  await page.getByLabel('약').selectOption('301');
  await page.getByLabel('복용 일시').fill('2026-09-03T15:20');
  await page.getByLabel('복용 후 느낀 점').fill('계정 A의 메모');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByText('계정 A의 메모')).toBeVisible();

  const otherPage = await page.context().newPage();
  await otherPage.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'feature-252-medication-token');
    sessionStorage.setItem('poke.account-principal', 'feature-252-other@example.com');
  });
  await otherPage.goto('/medications/notes');
  await expect(otherPage.getByText('계정 A의 메모')).toHaveCount(0);
  await expect(otherPage.getByText('복용 후 느낀 점을 남겨두면 다음 진료 때 도움이 돼요.')).toBeVisible();
  await otherPage.close();

  await page.reload();
  await expect(page.getByText('계정 A의 메모')).toBeVisible();
});

test('복약 메모는 작성·수정·삭제할 수 있다', async ({ page }) => {
  await page.goto('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '새 메모 작성' }).click();
  await expect(page).toHaveURL('/medications/notes/new');
  await page.getByLabel('처방').selectOption('12');
  await page.getByLabel('약').selectOption('301');
  await page.getByLabel('복용 일시').fill('2026-09-03T15:20');
  await page.getByLabel('복용 후 느낀 점').fill('속이 편해졌어요.');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect(page).toHaveURL('/medications/notes');
  await expect(page.getByText('속이 편해졌어요.')).toBeVisible();
  await page.getByRole('button', { name: /속이 편해졌어요/ }).click();
  await expect(page).toHaveURL(/\/medications\/notes\/[^/]+/);
  await page.getByLabel('복용 후 느낀 점').fill('수정한 메모예요.');
  await page.getByRole('button', { name: '수정 저장' }).click();
  await expect(page.getByText('수정한 메모예요.')).toBeVisible();

  await page.getByRole('button', { name: /수정한 메모예요/ }).click();
  await expect(page).toHaveURL(/\/medications\/notes\/[^/]+/);
  await page.getByRole('button', { name: '삭제' }).click();
  await expect(page.getByRole('dialog')).toContainText('삭제한 복약 메모는 다시 볼 수 없어요.');
  await page.getByRole('dialog').getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes');
  await expect(page.getByText('수정한 메모예요.')).toHaveCount(0);
});

test('복약 메모 목록은 더 보기로 전체 개수를 유지하며 페이지를 이어서 연다', async ({ page }) => {
  await page.addInitScript(() => {
    const notes = Array.from({ length: 25 }, (_, index) => ({
      id: index + 1,
      careEpisodeId: 12,
      careEpisodeTitle: '2026-08-22 조제약 복약안내',
      careEpisodeAlias: '감기약',
      careEpisodeStartDate: '2026-08-22',
      careEpisodeStatus: 'ACTIVE',
      availableMedications: [],
      medicationId: null,
      medication: null,
      dosedAt: '2026-09-03T08:00:00',
      body: `페이지 메모 ${index + 1}`,
      createdAt: '2026-09-03T15:20:00',
      updatedAt: null,
    }));
    sessionStorage.setItem(
      'rxvita.mock.medication-notes:feature-252-medication%40example.com',
      JSON.stringify(notes),
    );
  });
  await page.goto('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모 25개', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '더 보기', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '더 보기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '복약 메모 25개', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '더 보기', exact: true })).toHaveCount(0);
});

test('복약 메모 저장 실패는 입력을 보존하고 재시도할 수 있다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('rxvita.mock.medication-notes:fail-create-once', '1');
  });

  await page.goto('/medications/notes/new');
  await page.getByLabel('처방').selectOption('12');
  await page.getByLabel('복용 일시').fill('2026-09-03T15:20');
  await page.getByLabel('복용 후 느낀 점').fill('재시도 메모');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('잠시 후 다시 시도해주세요.');
  await expect(page.getByLabel('복용 후 느낀 점')).toHaveValue('재시도 메모');
  await expect(page.getByRole('button', { name: '저장', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page).toHaveURL('/medications/notes');
  await expect(page.getByText('재시도 메모', { exact: true })).toBeVisible();
});

test('복약 메모 저장·삭제 중 중복 클릭을 하나의 요청으로 제한한다', async ({ page }) => {
  await page.goto('/medications/notes/new');
  await page.getByLabel('처방').selectOption('12');
  await page.getByLabel('약').selectOption('301');
  await page.getByLabel('복용 일시').fill('2026-09-03T15:20');
  await page.getByLabel('복용 후 느낀 점').fill('중복 저장 방지 메모');

  const saveButton = page.getByRole('button', { name: /저장/ }).filter({ hasText: '저장' });
  await saveButton.click();
  await expect(saveButton).toBeDisabled();
  await saveButton.evaluate((button) => {
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  await expect(page).toHaveURL('/medications/notes');
  await expect(page.getByRole('heading', { name: '복약 메모 1개', exact: true })).toBeVisible();
  await expect(page.getByText('중복 저장 방지 메모', { exact: true })).toHaveCount(1);

  await page.getByRole('button', { name: /중복 저장 방지 메모/ }).click();
  const deleteButton = page.getByRole('button', { name: '삭제', exact: true });
  await deleteButton.click();
  const confirmDeleteButton = page.getByRole('dialog').getByRole('button', { name: /^삭제/ });
  await confirmDeleteButton.click();
  await expect(confirmDeleteButton).toBeDisabled();
  await confirmDeleteButton.evaluate((button) => {
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  await expect(page).toHaveURL('/medications/notes');
  await expect(page.locator('#medication-notes-title')).toBeVisible();
  await expect(page.getByText('중복 저장 방지 메모', { exact: true })).toHaveCount(0);
});

test('취소된 과거 처방 메모도 원래 처방을 보존한 채 수정할 수 있다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem(
      'rxvita.mock.medication-notes:feature-252-medication%40example.com',
      JSON.stringify([
        {
          id: 404,
          careEpisodeId: 999,
          careEpisodeTitle: '2025-01-15 조제약 복약안내',
          careEpisodeAlias: '지난 겨울 처방',
          careEpisodeStartDate: '2025-01-15',
          careEpisodeStatus: 'CANCELLED',
          availableMedications: [],
          medicationId: null,
          medication: null,
          dosedAt: '2025-01-16T08:00:00',
          body: '기존 메모',
          createdAt: '2025-01-16T08:00:00',
          updatedAt: null,
        },
      ]),
    );
  });

  await page.goto('/medications/notes/404');
  await expect(page.getByLabel('처방')).toBeDisabled();
  await expect(page.getByLabel('처방').locator('option:checked')).toHaveText('지난 겨울 처방');
  await expect(page.getByText('약이 삭제되었거나 처방 전체에 대한 메모예요.')).toBeVisible();
  await page.getByLabel('복용 일시').fill('2025-01-16T09:30');
  await page.getByLabel('복용 후 느낀 점').fill('과거 처방도 수정했어요.');
  await page.getByRole('button', { name: '수정 저장', exact: true }).click();

  await expect(page).toHaveURL('/medications/notes');
  await expect(page.getByText('지난 겨울 처방', { exact: true })).toBeVisible();
  await expect(page.getByText('과거 처방도 수정했어요.', { exact: true })).toBeVisible();
});
