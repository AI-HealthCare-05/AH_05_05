import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const ACCESS_TOKEN = 'e2e-document-token';
const DOCUMENT_ID = 501;
const OCR_URL = `/api/v1/ocr/jobs/${DOCUMENT_ID}`;
const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8+QAAAABJRU5ErkJggg==',
  'base64',
);

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

interface CapturedRequest {
  url: string;
  headers: Record<string, string>;
  body: string;
  requestedAt: number;
}

interface DocumentApiTrace {
  uploads: CapturedRequest[];
  polls: CapturedRequest[];
  images: CapturedRequest[];
  patches: CapturedRequest[];
  scheduleRequests: CapturedRequest[];
  settingsRequests: CapturedRequest[];
}

const readyOcrResult = {
  batchId: 'ocr-batch-501',
  ocrStatus: 'ready_for_review',
  documentImageUrl: '/server-does-not-authorize-img-tags',
  fields: {
    dispensedDate: { value: '2026-08-22', confidence: 'high' },
  },
  medications: [
    {
      tempId: 'm1',
      name: '셀레콕시브',
      strength: '200mg',
      doseQuantity: '1정',
      timesPerDay: 2,
      days: 7,
      confidence: 'high',
    },
    {
      tempId: 'm2',
      name: '리바록사반',
      strength: '10mg',
      doseQuantity: '1정',
      timesPerDay: 2,
      days: 7,
      confidence: 'low',
    },
    {
      tempId: 'm3',
      name: '아세트아미노펜',
      strength: '650mg',
      doseQuantity: '1정',
      days: 7,
      confidence: 'high',
    },
    {
      tempId: 'm4',
      name: ' 파모티딘 원문 ',
      confidence: 'high',
    },
  ],
  lowConfidenceCount: 1,
};

const template04ScheduleMedications = [
  {
    medicationId: 901,
    name: '세프디니르건조시럽',
    dose: '5mL',
    timesPerDay: 2,
    timing: '식후에 복용하세요. 복용 전 충분히 흔들어 주세요.',
    slots: [],
  },
  {
    medicationId: 902,
    name: '암브록솔시럽',
    dose: '5mL',
    timesPerDay: 3,
    timing: '식후에 복용하세요. 충분한 수분을 섭취하세요.',
    slots: [],
  },
  {
    medicationId: 903,
    name: '슈도에페드린시럽',
    dose: '5mL',
    timesPerDay: 2,
    timing: '아침과 점심 식후에 복용하세요.',
    slots: [],
  },
  {
    medicationId: 904,
    name: '프로바이오틱스분말',
    dose: '1포',
    timesPerDay: 2,
    timing: '식후 미지근한 물에 타서 복용하세요.',
    slots: [],
  },
] as const;

function capture(route: Route): CapturedRequest {
  const request = route.request();
  return {
    url: request.url(),
    headers: request.headers(),
    body: request.postDataBuffer()?.toString('utf8') ?? '',
    requestedAt: Date.now(),
  };
}

async function authenticate(page: Page) {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'ocr-e2e@example.com');
  }, ACCESS_TOKEN);
}

async function stubNotificationPermission(
  page: Page,
  permission: NotificationPermission,
  requestedPermission: NotificationPermission = 'granted',
) {
  await page.addInitScript(
    ({ initialPermission, nextPermission }) => {
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

async function stubPushManager(page: Page, alreadyRegistered = true) {
  await page.addInitScript(({ hasExistingSubscription }) => {
    const subscription = {
      endpoint: 'https://push.example.test/real-feature-252-device',
      expirationTime: null,
      keys: { p256dh: 'real-feature-252-p256dh', auth: 'real-feature-252-auth' },
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

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function interceptDocumentRegistration(page: Page): Promise<DocumentApiTrace> {
  const trace: DocumentApiTrace = {
    uploads: [],
    polls: [],
    images: [],
    patches: [],
    scheduleRequests: [],
    settingsRequests: [],
  };
  let pollIndex = 0;
  const pendingOcrResults = [
    { batchId: 'ocr-batch-501', ocrStatus: 'queued' },
    { batchId: 'ocr-batch-501', ocrStatus: 'processing' },
  ];

  await page.route(/\/api\/v1\/ocr(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (request.method() === 'POST' && path === '/api/v1/ocr') {
      trace.uploads.push(capture(route));
      await fulfillJson(route, {
        batchId: 'upload-response-is-not-the-polling-id',
        documentIds: [DOCUMENT_ID],
        ocrStatus: 'queued',
      });
      return;
    }

    if (request.method() === 'GET' && path === OCR_URL) {
      trace.polls.push(capture(route));
      const response = pendingOcrResults[pollIndex] ?? readyOcrResult;
      pollIndex += 1;
      await fulfillJson(route, response);
      return;
    }

    if (
      request.method() === 'GET' &&
      (path === `/api/v1/ocr/jobs/${DOCUMENT_ID}/image` ||
        path === `/api/v1/ocr/jobs/${DOCUMENT_ID}/processed-image`)
    ) {
      trace.images.push(capture(route));
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }

    if (request.method() === 'PATCH' && path === OCR_URL) {
      trace.patches.push(capture(route));
      await fulfillJson(route, { recordId: 314, hasMedication: true, statusCode: 'active' });
      return;
    }

    await route.continue();
  });

  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    trace.scheduleRequests.push(capture(route));
    await fulfillJson(route, {
      start: null,
      mealTimes: null,
      medications: [
        {
          medicationId: 801,
          name: '리바록사반 수정',
          dose: '10mg',
          timesPerDay: 2,
          timing: '아침·저녁 식후',
          slots: [],
        },
      ],
    });
  });

  let settings = {
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
    if (route.request().method() === 'GET') {
      await fulfillJson(route, settings);
      return;
    }
    if (route.request().method() === 'PATCH') {
      trace.settingsRequests.push(capture(route));
      settings = {
        ...settings,
        ...(route.request().postDataJSON() as Partial<typeof settings>),
        notifyConsentedAt: new Date().toISOString(),
      };
      await fulfillJson(route, settings);
      return;
    }
    await route.continue();
  });

  return trace;
}

async function selectGalleryPng(page: Page) {
  await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({
    name: 'medication-envelope.png',
    mimeType: 'image/png',
    buffer: ONE_PIXEL_PNG,
  });
}

test('OCR 검토는 전처리 이미지를 작게 맞춰 보여주고 확대 화면에서 원본으로 전환한다', async ({ page }) => {
  await authenticate(page);
  const requestedImages: string[] = [];

  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(route, { ...readyOcrResult, batchId: 'b_mock_9f21' });
      return;
    }
    if (
      request.method() === 'GET' &&
      (path === '/api/v1/ocr/jobs/b_mock_9f21/processed-image' ||
        path === '/api/v1/ocr/jobs/b_mock_9f21/image')
    ) {
      requestedImages.push(path);
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    await route.continue();
  });

  await page.goto('/dev/ocr-review');

  const preview = page.getByRole('img', { name: '전처리한 약봉투' });
  await expect(preview).toBeVisible();
  expect(await preview.evaluate((image) => getComputedStyle(image).objectFit)).toBe('contain');
  const previewBox = await preview.boundingBox();
  expect(previewBox).not.toBeNull();
  expect(previewBox!.height).toBeGreaterThanOrEqual(287);
  expect(previewBox!.height).toBeLessThanOrEqual(288);

  await page.getByRole('button', { name: '전처리한 약봉투 크게 보기' }).click();
  const viewer = page.getByRole('dialog');
  const enlarged = viewer.getByRole('img', { name: '확대한 전처리 약봉투' });
  await expect(enlarged).toBeVisible();
  const processedSrc = await enlarged.getAttribute('src');
  await expect(viewer.getByRole('button', { name: '전처리 후' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await viewer.getByRole('button', { name: '원본 보기' }).click();
  await expect(viewer.getByRole('img', { name: '확대한 약봉투 원본' })).toBeVisible();
  await expect(viewer.getByRole('img', { name: '확대한 약봉투 원본' })).not.toHaveAttribute(
    'src',
    processedSrc ?? '',
  );
  expect(requestedImages).toEqual([
    '/api/v1/ocr/jobs/b_mock_9f21/processed-image',
    '/api/v1/ocr/jobs/b_mock_9f21/image',
  ]);
});

test('OCR 검토의 직접 추가 버튼과 입력 제한을 간결하게 표시한다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(route, { ...readyOcrResult, batchId: 'b_mock_9f21' });
      return;
    }
    if (
      request.method() === 'GET' &&
      (path === '/api/v1/ocr/jobs/b_mock_9f21/processed-image' ||
        path === '/api/v1/ocr/jobs/b_mock_9f21/image')
    ) {
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    await route.continue();
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible();
  await expect(page.getByText('복용 시작일을 이 날짜로 채워둘게요.')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '빠진 약 직접 추가' })).toHaveCount(0);

  const directAdd = page.getByRole('button', { name: '직접 추가', exact: true });
  await expect(directAdd).toBeVisible();
  await directAdd.click();

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: '약 추가' })).toBeVisible();
  await expect(dialog.getByText('약봉투와 다른 내용만 고쳐주세요.')).toHaveCount(0);

  const name = dialog.getByLabel('약품명');
  const strength = dialog.getByLabel('함량');
  const doseQuantity = dialog.getByLabel('1회 투약량');
  const days = dialog.getByLabel('복용 일수');
  await expect(name).toHaveAttribute('maxlength', '100');
  await expect(strength).toHaveAttribute('maxlength', '50');
  await expect(doseQuantity).toHaveAttribute('maxlength', '50');
  await expect(days).toHaveAttribute('maxlength', '3');
  await expect(days).toHaveAttribute('inputmode', 'numeric');
  expect(
    await name.evaluate((input) =>
      getComputedStyle(input.parentElement?.parentElement ?? input).paddingLeft,
    ),
  ).toBe('4px');

  await days.fill('999');
  await expect(days).toHaveValue('');
  await days.fill('365');
  await expect(days).toHaveValue('365');
});

test('OCR 결과를 확정하면 해당 복약 시간 설정 화면으로 이동한다', async ({ page }) => {
  await authenticate(page);
  const scheduleRequests: CapturedRequest[] = [];

  await page.route('**/api/v1/ocr/jobs/b_mock_9f21', async (route) => {
    if (route.request().method() === 'PATCH') {
      await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      return;
    }
    await fulfillJson(route, {
      ...readyOcrResult,
      batchId: 'b_mock_9f21',
      medications: [{ ...readyOcrResult.medications[0] }],
      lowConfidenceCount: 0,
    });
  });
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/image', async (route) => {
    await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
  });
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    scheduleRequests.push(capture(route));
    await fulfillJson(route, {
      start: null,
      mealTimes: null,
      medications: [
        {
          medicationId: 801,
          name: '셀레콕시브',
          dose: '200mg',
          timesPerDay: 2,
          timing: '아침·저녁 식후',
          slots: [],
        },
      ],
    });
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: /저장/ }).click();

  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21',
  );
  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-22');
  expect(scheduleRequests.length).toBeGreaterThan(0);
  expect(
    scheduleRequests.every(
      (request) =>
        new URL(request.url).pathname === '/api/v1/med/medication/schedule/315' &&
        new URL(request.url).search === '',
    ),
  ).toBe(true);

  const requestCountBeforeReload = scheduleRequests.length;
  await page.reload();
  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-22');
  expect(scheduleRequests.length).toBeGreaterThan(requestCountBeforeReload);
  expect(new URL(scheduleRequests.at(-1)!.url).pathname).toBe(
    '/api/v1/med/medication/schedule/315',
  );
  expect(new URL(scheduleRequests.at(-1)!.url).search).toBe('');
});

test('recordId 없는 복약 시간 직접 진입은 임의 기록을 조회하지 않는다', async ({ page }) => {
  await authenticate(page);
  const scheduleRequests: CapturedRequest[] = [];
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    scheduleRequests.push(capture(route));
    await fulfillJson(route, { start: null, mealTimes: null, medications: [] });
  });

  await page.goto('/medication-schedule');

  await expect(page.getByText('복약 기록을 선택해주세요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '약봉투 등록하기' })).toBeVisible();
  expect(scheduleRequests).toHaveLength(0);
});

test('복용 시작 전에도 API의 사용자 설정 시간이 프런트 기본값보다 우선한다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, {
      start: null,
      mealTimes: {
        morning: '07:30',
        lunch: '12:00',
        evening: '18:00',
        bedtime: '21:30',
      },
      medications: template04ScheduleMedications,
    });
  });

  await page.goto('/medication-schedule?recordId=904&ocrJobId=b_mock_9f21');

  await expect(page.getByRole('button', { name: /아침약 07:30/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /점심약 12:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /저녁약 18:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /취침약 21:30/ })).toBeVisible();
});

test('복약 시간 설정은 봉투에서 시간대를 읽은 약도 숨기지 않는다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, {
      start: null,
      mealTimes: null,
      medications: template04ScheduleMedications,
    });
  });

  await page.goto('/medication-schedule?recordId=904&ocrJobId=b_mock_9f21');

  await expect(page.getByRole('button', { name: /아침약 08:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /점심약 13:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /저녁약 19:00/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /취침약 22:00/ })).toBeVisible();

  await expect(page.getByText('세프디니르건조시럽 5mL', { exact: true })).toBeVisible();
  await expect(page.getByText('암브록솔시럽 5mL', { exact: true })).toBeVisible();
  await expect(page.getByText('슈도에페드린시럽 5mL', { exact: true })).toBeVisible();
  await expect(page.getByText('프로바이오틱스분말 1포', { exact: true })).toBeVisible();

  const pseudoMorning = page.getByRole('button', { name: '슈도에페드린시럽 아침약' });
  const pseudoLunch = page.getByRole('button', { name: '슈도에페드린시럽 점심약' });
  await expect(pseudoMorning).toHaveAttribute('aria-pressed', 'true');
  await expect(pseudoLunch).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('button', { name: '시작 아침약' }).click();
  await pseudoMorning.click();
  await pseudoLunch.click();

  await expect(page.getByText('복용 시간을 하나 이상 선택해주세요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '저장하고 계속' })).toBeDisabled();
});

test('복약 시간 저장 실패 후 같은 path와 본문으로 재시도한다', async ({ page }) => {
  await authenticate(page);
  // 이 테스트는 저장 재시도 계약만 검증합니다. 알림 권한 흐름은 별도 테스트에서 다룹니다.
  await page.addInitScript(() => Reflect.deleteProperty(window, 'Notification'));
  const putRequests: CapturedRequest[] = [];

  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, {
        start: null,
        mealTimes: null,
        medications: template04ScheduleMedications,
      });
      return;
    }

    putRequests.push(capture(route));
    if (putRequests.length === 1) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'temporary_error', message: '잠시 후 다시 시도해주세요.' }),
      });
      return;
    }
    await fulfillJson(route, { saved: true });
  });

  await page.goto('/medication-schedule?recordId=904&ocrJobId=b_mock_9f21');
  await page.getByRole('button', { name: '알람 없이 저장' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: '다시 시도' }).click();

  await expect(page).toHaveURL('/home');
  expect(putRequests).toHaveLength(2);
  expect(putRequests.every((request) => new URL(request.url).pathname === '/api/v1/med/medication/schedule/904')).toBe(
    true,
  );
  expect(putRequests.every((request) => new URL(request.url).search === '')).toBe(true);
  const payloads = putRequests.map((request) => JSON.parse(request.body) as Record<string, unknown>);
  expect(payloads[0]).toEqual(payloads[1]);
  expect(payloads.every((payload) => !('recordId' in payload))).toBe(true);
  expect(payloads.every((payload) => !('isNotifyMedication' in payload))).toBe(true);
  expect(payloads[0].mealTimes).toEqual({
    morning: '08:00',
    lunch: '13:00',
    evening: '19:00',
    bedtime: '22:00',
  });
  expect(
    (payloads[0].medications as Array<{ slots: string[] }>).every(
      (medication) => medication.slots.length > 0,
    ),
  ).toBe(true);
});

test('복약 시간 설정의 뒤로가기는 완료된 OCR의 4개 약 검토 화면으로 돌아간다', async ({
  page,
}) => {
  await authenticate(page);
  let confirmed = false;

  await page.route('**/api/v1/ocr/jobs/b_mock_9f21', async (route) => {
    if (route.request().method() === 'PATCH') {
      confirmed = true;
      await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      return;
    }
    await fulfillJson(route, {
      ...readyOcrResult,
      batchId: 'b_mock_9f21',
      ocrStatus: confirmed ? 'complete' : 'ready_for_review',
      medications: readyOcrResult.medications.map((medication) => ({
        ...medication,
        confidence: 'high',
      })),
      lowConfidenceCount: 0,
    });
  });
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/image', async (route) => {
    await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
  });
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, {
      start: null,
      mealTimes: null,
      medications: template04ScheduleMedications,
    });
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21',
  );

  await page.reload();
  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page).toHaveURL(
    '/ocr-review?batchId=b_mock_9f21&recordId=315&mode=confirmed',
  );
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible();
  await expect(page.getByText('이미 등록된 약봉투예요')).toHaveCount(0);

  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21',
  );
  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-22');
});

test('사용자가 바꾼 복용 시작일은 OCR 검토 화면을 다녀와도 유지된다', async ({ page }) => {
  await authenticate(page);
  let confirmed = false;

  await page.route('**/api/v1/ocr/jobs/b_mock_9f21', async (route) => {
    if (route.request().method() === 'PATCH') {
      confirmed = true;
      await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      return;
    }
    await fulfillJson(route, {
      ...readyOcrResult,
      batchId: 'b_mock_9f21',
      ocrStatus: confirmed ? 'complete' : 'ready_for_review',
      medications: readyOcrResult.medications.map((medication) => ({
        ...medication,
        confidence: 'high',
      })),
      lowConfidenceCount: 0,
    });
  });
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/image', async (route) => {
    await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
  });
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, {
      start: null,
      mealTimes: null,
      medications: template04ScheduleMedications,
    });
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-22');

  await page.getByLabel('복용 시작 날짜').fill('2026-08-20');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-20');
});

function expectAuthenticated(requests: CapturedRequest[]) {
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every((request) => request.headers.authorization === `Bearer ${ACCESS_TOKEN}`)).toBe(
    true,
  );
}

test('갤러리 입력은 JPG/PNG 한 장만 받고 카메라 입력과 분리되어 있다', async ({ page }) => {
  await page.goto('/document-upload');

  const camera = page.getByLabel('카메라로 약봉투 촬영');
  const gallery = page.getByLabel('갤러리에서 약봉투 선택');
  await expect(camera).toHaveAttribute('accept', 'image/jpeg,image/png');
  await expect(camera).toHaveAttribute('capture', 'environment');
  await expect(camera).not.toHaveAttribute('multiple');
  await expect(gallery).toHaveAttribute('accept', 'image/jpeg,image/png');
  await expect(gallery).not.toHaveAttribute('capture');
  await expect(gallery).not.toHaveAttribute('multiple');
});

test('선택한 약봉투 사진을 누르면 전체 화면 원본을 열고 닫을 수 있다', async ({ page }) => {
  await page.goto('/document-upload');
  await selectGalleryPng(page);

  await page.getByRole('button', { name: '선택한 약봉투 크게 보기' }).click();

  const viewer = page.getByRole('dialog');
  await expect(viewer).toBeVisible();
  await expect(viewer.getByRole('img', { name: '확대한 약봉투 원본' })).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(viewer).toHaveCount(0);
});

test('조제일은 서울 오늘로부터 31일 뒤까지 수정하고 저장할 수 있다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await authenticate(page);
  const patches: CapturedRequest[] = [];

  await page.route('**/api/v1/ocr/jobs/b_mock_9f21', async (route) => {
    if (route.request().method() === 'PATCH') {
      patches.push(capture(route));
      await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      return;
    }
    await fulfillJson(route, {
      ...readyOcrResult,
      batchId: 'b_mock_9f21',
      medications: [{ ...readyOcrResult.medications[0] }],
      lowConfidenceCount: 0,
    });
  });
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/image', async (route) => {
    await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
  });
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, { start: null, mealTimes: null, medications: [] });
  });

  await page.goto('/dev/ocr-review');
  const dispensedDate = page.getByLabel('조제일');
  await expect(dispensedDate).toHaveAttribute('max', '2026-09-25');
  await dispensedDate.fill('2026-09-25');
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();

  await expect(page).toHaveURL('/medication-schedule?recordId=315&ocrJobId=b_mock_9f21');
  expect(patches).toHaveLength(1);
  expect((JSON.parse(patches[0].body) as { dispensedDate: string }).dispensedDate).toBe(
    '2026-09-25',
  );
});

test('인증된 문서 OCR 계약으로 결과를 검토·수정하고 저장한다', async ({ page }) => {
  test.slow();
  await authenticate(page);
  const trace = await interceptDocumentRegistration(page);
  await page.goto('/document-upload');
  await selectGalleryPng(page);

  const uploadPreview = page.getByRole('img', { name: '선택한 약봉투 미리보기' });
  await expect(uploadPreview).toBeVisible();
  const previewBox = await uploadPreview.boundingBox();
  expect(previewBox).not.toBeNull();
  expect(previewBox!.width).toBeGreaterThanOrEqual(previewBox!.height);
  await expect(page.getByText('medication-envelope.png')).toBeVisible();
  await page.getByRole('button', { name: '등록하기' }).click();

  await expect(page).toHaveURL('/ocr-review');
  await expect(page.getByRole('heading', { name: '약봉투를 읽고 있어요' })).toBeVisible();
  await expect(page.getByText('잠깐이면 끝나요. 그동안 둘러보세요.')).toBeVisible();
  const carousel = page.getByRole('region', { name: 'RxVita 기능 소개' });
  const stage = page.getByRole('status', { name: '약봉투 판독 단계' });
  await expect(carousel).toBeVisible();
  await expect(stage).toContainText('글자를 찾고 있어요');
  await expect(stage).toContainText('2 / 3 단계');
  await expect(page.getByRole('heading', { name: '약 4개' })).toHaveCount(0);

  const carouselBox = await carousel.boundingBox();
  const stageBox = await stage.boundingBox();
  expect(carouselBox).not.toBeNull();
  expect(stageBox).not.toBeNull();
  expect(carouselBox!.y + carouselBox!.height).toBeLessThanOrEqual(stageBox!.y);

  await expect(stage).toContainText('약 이름을 정리하고 있어요', { timeout: 4_500 });
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible({ timeout: 5_000 });

  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible();
  await expect(page.getByLabel('조제일')).toHaveValue('2026-08-22');
  await expect(page.getByText('1곳만 확인해주세요')).toBeVisible();
  await expect(page.getByText('확인 필요', { exact: true })).toHaveCount(1);
  await expect(page.getByRole('img', { name: '전처리한 약봉투' })).toHaveAttribute(
    'src',
    /^blob:/,
  );

  await expect(page.getByRole('button', { name: /파모티딘 원문/ })).toContainText('함량 미추출');
  await expect(page.getByRole('button', { name: /파모티딘 원문/ })).toContainText('1회 투약량 미추출');
  await expect(page.getByRole('button', { name: /파모티딘 원문/ })).toContainText('1일 횟수 미추출');
  await expect(page.getByRole('button', { name: /파모티딘 원문/ })).toContainText('투약일수 미추출');

  await page.getByRole('button', { name: /리바록사반 10mg/ }).click();
  const editDialog = page.getByRole('dialog');
  await editDialog.getByLabel('약품명').fill('리바록사반 수정');
  await editDialog.getByLabel('함량').fill('15mg');
  await editDialog.getByLabel('1회 투약량').fill('0.5정');
  await editDialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('button', { name: /리바록사반 수정 15mg/ })).toBeVisible();

  await page.getByRole('button', { name: /아세트아미노펜 650mg/ }).click();
  const prnDialog = page.getByRole('dialog');
  await prnDialog.getByRole('combobox').click();
  await page.getByRole('option', { name: '필요 시', exact: true }).click();
  await prnDialog.getByRole('button', { name: '저장', exact: true }).click();

  await page.getByRole('button', { name: /파모티딘 원문/ }).click();
  const sourceNameDialog = page.getByRole('dialog');
  await sourceNameDialog.getByLabel('1회 투약량').fill('0.75');
  await sourceNameDialog.getByRole('button', { name: '저장', exact: true }).click();

  await page.getByRole('button', { name: '직접 추가', exact: true }).click();
  const addDialog = page.getByRole('dialog');
  await addDialog.getByLabel('약품명').fill('새 약');
  await addDialog.getByLabel('함량').fill('500mg');
  await addDialog.getByLabel('1회 투약량').fill('1캡슐');
  await addDialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 5개' })).toBeVisible();

  await page.getByRole('button', { name: /셀레콕시브 200mg/ }).click();
  const deleteDialog = page.getByRole('dialog');
  await deleteDialog.getByRole('button', { name: '이 약 삭제' }).click();
  await deleteDialog.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('button', { name: /셀레콕시브 200mg/ })).toHaveCount(0);

  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '확인 후 저장' }).click();
  await expect(page).toHaveURL('/medication-schedule?recordId=314&ocrJobId=501');
  await expect(page.getByLabel('복용 시작 날짜')).toHaveValue('2026-08-22');

  expectAuthenticated(trace.uploads);
  expect(trace.uploads.every((request) => request.headers['content-type']?.startsWith('multipart/form-data;'))).toBe(true);
  expect(trace.uploads.every((request) => !request.body.includes('name="purpose"'))).toBe(true);
  expect(trace.uploads.every((request) => request.body.includes('name="file"') && request.body.includes('filename="medication-envelope.png"'))).toBe(true);
  const idempotencyKeys = trace.uploads.map((request) => request.headers['idempotency-key']);
  expect(idempotencyKeys.every(Boolean)).toBe(true);
  expect(new Set(idempotencyKeys).size).toBe(1);

  expect(trace.polls).toHaveLength(3);
  expect(trace.polls.every((request) => new URL(request.url).pathname === OCR_URL)).toBe(true);
  expect(trace.polls[0].requestedAt - trace.uploads.at(-1)!.requestedAt).toBeGreaterThanOrEqual(0);
  expect(trace.polls[1].requestedAt - trace.polls[0].requestedAt).toBeGreaterThanOrEqual(1_800);
  expect(trace.polls[2].requestedAt - trace.polls[1].requestedAt).toBeGreaterThanOrEqual(1_800);
  expectAuthenticated(trace.polls);
  expectAuthenticated(trace.images);

  expect(trace.patches).toHaveLength(1);
  expectAuthenticated(trace.patches);
  const patchPayload = JSON.parse(trace.patches[0].body) as {
    dispensedDate: string;
    medications: Array<Record<string, unknown>>;
  };
  expect(Object.keys(patchPayload).sort()).toEqual(['dispensedDate', 'medications']);
  expect(patchPayload.dispensedDate).toBe('2026-08-22');
  expect(patchPayload.medications).toHaveLength(4);
  expect(patchPayload.medications).toEqual(
    expect.arrayContaining([
      {
        tempId: 'm2',
        name: '리바록사반 수정',
        strength: '15mg',
        doseQuantity: '0.5정',
        timesPerDay: 2,
        days: 7,
      },
      { tempId: 'm3', name: '아세트아미노펜', strength: '650mg', doseQuantity: '1정', timesPerDay: null, days: 7 },
      { tempId: 'm4', name: ' 파모티딘 원문 ', doseQuantity: '0.75' },
      {
        tempId: expect.stringMatching(/^new_/),
        name: '새 약',
        strength: '500mg',
        doseQuantity: '1캡슐',
      },
    ]),
  );
  expect(
    patchPayload.medications.every(
      (medication) =>
        !('confidence' in medication) &&
        !('dose' in medication) &&
        !('efficacy' in medication) &&
        !('administration' in medication) &&
        !('precautions' in medication),
    ),
  ).toBe(true);
  expect(patchPayload.medications).not.toEqual(
    expect.arrayContaining([expect.objectContaining({ tempId: 'm1' })]),
  );

  expect(trace.scheduleRequests.length).toBeGreaterThan(0);
  expect(
    trace.scheduleRequests.every(
      (request) => new URL(request.url).pathname === '/api/v1/med/medication/schedule/314',
    ),
  ).toBe(true);
});

test('등록 5단계의 알람 선택과 시각을 기존 설정 PATCH payload에 포함한다', async ({ page }) => {
  test.slow();
  await authenticate(page);
  await stubNotificationPermission(page, 'granted');
  await stubPushManager(page, true);
  const trace = await interceptDocumentRegistration(page);
  const pushPayloads: unknown[] = [];
  let releasePushRegistration!: () => void;
  const pushRegistrationSettled = new Promise<void>((resolve) => {
    releasePushRegistration = resolve;
  });
  await page.route('**/api/v1/alarms/push-subscriptions', async (route) => {
    pushPayloads.push(route.request().postDataJSON());
    await pushRegistrationSettled;
    await fulfillJson(route, { id: 1 });
  });
  await page.goto('/ocr-review?batchId=501');

  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible({ timeout: 10_000 });
  await page.getByLabel('복약 별칭').fill('실 API 알람 처방');
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '확인 후 저장' }).click();
  await expect(page).toHaveURL(/\/medication-schedule\?recordId=314&ocrJobId=501/);

  await expect(page.getByText('3 / 5', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '시작 아침약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();

  const medicationNotifications = page.getByRole('switch', { name: '복약 알림' });
  await medicationNotifications.click();
  const completionButton = page.getByRole('button', { name: '등록 완료', exact: true });
  await expect(completionButton).toBeDisabled();
  await completionButton.evaluate((button) => {
    button.removeAttribute('disabled');
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toHaveCount(0);
  await expect(page).toHaveURL(/\/medication-schedule\?/);
  await expect.poll(() => trace.settingsRequests.length).toBe(0);
  expect(pushPayloads).toHaveLength(1);

  releasePushRegistration();
  await expect(medicationNotifications).toBeChecked();
  await expect(completionButton).toBeEnabled();
  expect(await page.evaluate(() => {
    const state = window as Window & { __feature252PushSubscribeCalls: number };
    return state.__feature252PushSubscribeCalls;
  })).toBe(0);
  await page.getByRole('button', { name: '아침약 알람 시간' }).click();
  const timeDialog = page.getByRole('dialog');
  await timeDialog.getByLabel('시').click();
  await page.getByRole('option', { name: '07시' }).click();
  await timeDialog.getByLabel('분').click();
  await page.getByRole('option', { name: '30분' }).click();
  await timeDialog.getByRole('button', { name: '이 시간 적용' }).click();
  await completionButton.click();
  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  await expect(page.getByText(/알림 07:30/)).toBeVisible();

  const settingsPatch = trace.settingsRequests.find((request) => request.url.includes('/me/settings'));
  expect(settingsPatch).toBeDefined();
  expect(JSON.parse(settingsPatch!.body)).toMatchObject({
    notifyMedication: true,
    morningMedicationTime: '07:30',
    lunchMedicationTime: '13:00',
    eveningMedicationTime: '19:00',
    bedtimeMedicationTime: '22:00',
  });
  expect(pushPayloads).toEqual([
    {
      endpoint: 'https://push.example.test/real-feature-252-device',
      p256dh_key: 'real-feature-252-p256dh',
      auth_key: 'real-feature-252-auth',
      platform: 'web',
      user_agent: expect.any(String),
    },
  ]);
});

test('로그인 홈은 v1 복약 개요의 빈 목록을 등록 상태로 보여준다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/medications', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'http_404', message: 'Not Found' }),
    });
  });
  await page.route('**/api/v1/medications', async (route) => {
    await fulfillJson(route, {
      recordId: 0,
      documentImageUrl: '',
      start: { date: '2026-08-26', slot: 'morning' },
      endDate: '2026-08-26',
      daysRemaining: 0,
      mealTimes: {
        morning: '08:00',
        lunch: '13:00',
        evening: '19:00',
        bedtime: '22:00',
      },
      medications: [],
    });
  });

  await page.goto('/home');

  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toHaveCount(0);
});

test('400일 전 ACTIVE 회차는 from을 처방 시작일로 유지한다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const ranges: URL[] = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    ranges.push(new URL(route.request().url()));
    await fulfillJson(route, []);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [
    {
      recordId: 400,
      documentImageUrl: '/mock/medication-envelope.svg',
      start: { date: '2025-07-21', slot: 'morning' },
      endDate: '2025-08-10',
      daysRemaining: 0,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
      medications: [
        {
          medicationId: 400,
          name: '지난 처방',
          dose: '1정',
          days: 21,
          daysRemaining: 0,
          slots: ['morning'],
          asNeeded: false,
        },
      ],
    },
  ]));

  await page.goto('/home');
  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
  expect(ranges).toHaveLength(1);
  expect(ranges[0].searchParams.get('from')).toBe('2025-07-21');
  expect(ranges[0].searchParams.get('to')).toBe('2025-08-10');
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toHaveCount(0);
});

test('365일 처방과 새 30일 회차는 정확히 366일 범위로 복약 기록을 조회한다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const ranges: URL[] = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    ranges.push(new URL(route.request().url()));
    await fulfillJson(route, []);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/medications', (route) => fulfillJson(route, [
    {
      recordId: 365,
      documentImageUrl: '/mock/medication-envelope.svg',
      start: { date: '2025-08-25', slot: 'morning' },
      endDate: '2026-08-24',
      daysRemaining: 0,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
      medications: [
        {
          medicationId: 365,
          name: '365일 처방',
          dose: '1정',
          days: 365,
          daysRemaining: 0,
          slots: ['morning'],
          asNeeded: false,
        },
      ],
    },
    {
      recordId: 366,
      documentImageUrl: '/mock/medication-envelope.svg',
      start: { date: '2026-08-25', slot: 'morning' },
      endDate: '2026-09-23',
      daysRemaining: 30,
      mealTimes: { morning: '08:00', lunch: '13:00', evening: '19:00', bedtime: '22:30' },
      medications: [
        {
          medicationId: 366,
          name: '새 처방',
          dose: '1정',
          days: 30,
          daysRemaining: 30,
          slots: ['morning'],
          asNeeded: false,
        },
      ],
    },
  ]));

  await page.goto('/home');
  await expect(page.getByRole('tabpanel', { name: '오늘의 복약' })).toBeVisible();
  expect(ranges).toHaveLength(1);
  expect(ranges[0].searchParams.get('from')).toBe('2025-09-23');
  expect(ranges[0].searchParams.get('to')).toBe('2026-09-23');
  await expect(page.getByText('복약 정보를 불러오지 못했어요')).toHaveCount(0);
});

test('활성 처방이 두 건이어도 복용 기록은 사용자 단위로 한 번만 조회하고 저장한다', async ({
  page,
}) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const doseGets: string[] = [];
  const dosePosts: Array<Record<string, unknown>> = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      doseGets.push(request.url());
      await fulfillJson(route, [], 200);
      return;
    }
    dosePosts.push(request.postDataJSON() as Record<string, unknown>);
    await fulfillJson(route, request.postDataJSON(), 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.goto('/dev/home-multiple-episodes');
  const action = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' })
    .getByRole('button', { name: '3개 먹었어요' });
  await action.click();

  await expect(page.getByLabel('8월 25일 아침 먹은 기록')).toBeVisible();
  expect(doseGets).toHaveLength(1);
  expect(new URL(doseGets[0]).searchParams.has('recordId')).toBe(false);
  expect(Object.keys(dosePosts[0]).sort()).toEqual(['date', 'slot', 'taken']);
  expect(dosePosts).toEqual([
    { date: '2026-08-25', slot: 'morning', taken: true },
  ]);
});

test('복약 선택 삭제는 오류를 팝업에 남기고 재시도하면 목록에서 제거한다', async ({ page }) => {
  await authenticate(page);
  let deleteAttempts = 0;
  let deleted = false;
  const overview = {
    recordId: 12,
    documentImageUrl: '/mock/medication-envelope.svg',
    start: { date: '2026-08-22', slot: 'morning' },
    endDate: '2026-08-31',
    daysRemaining: 7,
    isFinished: false,
    mealTimes: {
      morning: '08:00',
      lunch: '13:00',
      evening: '19:00',
      bedtime: '22:30',
    },
    medications: [
      {
        medicationId: 301,
        name: '셀레콕시브',
        dose: '200mg',
        days: 10,
        daysRemaining: 7,
        slots: ['morning'],
        asNeeded: false,
      },
    ],
  };
  await page.route('**/api/v1/medications/12', async (route) => {
    deleteAttempts += 1;
    if (deleteAttempts === 1) {
      await fulfillJson(route, { code: 'MEDICATION_RECORD_FORBIDDEN', message: '금지됨' }, 403);
      return;
    }
    if (deleteAttempts === 2) {
      await fulfillJson(route, { code: 'SERVER_ERROR', message: '삭제 서버 오류' }, 500);
      return;
    }
    deleted = true;
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/v1/medications', (route) =>
    fulfillJson(route, deleted ? [] : [overview], 200),
  );

  await page.goto('/medications');
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ }).check();
  await page.getByRole('button', { name: '삭제하기' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: '1개를 삭제할까요?' })).toBeVisible();
  await expect(dialog).toContainText('삭제한 처방은 약봉투를 다시 등록해야 복구할 수 있어요.');
  await dialog.getByRole('button', { name: '삭제하기' }).click();
  await expect(dialog).toContainText('선택한 복약 정보를 삭제하지 못했어요. 다시 시도해주세요.');
  await dialog.getByRole('button', { name: '다시 시도' }).click();
  await expect(dialog).toContainText('선택한 복약 정보를 삭제하지 못했어요. 다시 시도해주세요.');
  await dialog.getByRole('button', { name: '다시 시도' }).click();

  await expect(page).toHaveURL('/medications');
  await expect(page.getByText('1개를 삭제했어요')).toBeVisible();
  await expect(page.getByText('이 기간에 등록한 처방이 없어요')).toBeVisible();
  await expect(page.getByRole('button', { name: '되돌리기' })).toHaveCount(0);
});

test('업로드 응답에 문서 ID가 없으면 polling을 시작하지 않는다', async ({ page }) => {
  await authenticate(page);
  let pollCount = 0;
  await page.route(/\/api\/v1\/ocr(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'POST' && path === '/api/v1/ocr') {
      await fulfillJson(route, {
        batchId: 'server-batch-kept-intact',
        documentIds: [],
        ocrStatus: 'queued',
      });
      return;
    }
    if (request.method() === 'GET') pollCount += 1;
    await route.continue();
  });

  await page.goto('/document-upload');
  await selectGalleryPng(page);
  await page.getByRole('button', { name: '등록하기' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: '업로드에 실패했어요' })).toBeVisible();
  await expect(dialog).toContainText('업로드 응답에 문서 ID가 없어요.');
  expect(pollCount).toBe(0);
});

test('원본 이미지가 실패해도 medium OCR 결과를 확인하고 저장한다', async ({ page }) => {
  await authenticate(page);
  const images: CapturedRequest[] = [];
  const patches: CapturedRequest[] = [];
  const mediumOnlyResult = {
    ...readyOcrResult,
    batchId: 'b_mock_9f21',
    medications: [{ ...readyOcrResult.medications[0], confidence: 'medium' }],
    lowConfidenceCount: 0,
  };

  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(route, mediumOnlyResult);
      return;
    }
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21/image') {
      images.push(capture(route));
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'image_unavailable', message: '원본 이미지를 불러올 수 없어요.' }),
      });
      return;
    }
    if (request.method() === 'PATCH' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      patches.push(capture(route));
      await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, {
      start: null,
      mealTimes: null,
      medications: [
        {
          medicationId: 901,
          name: '셀레콕시브',
          dose: '200mg',
          timesPerDay: 2,
          timing: '아침·저녁 식후',
          slots: [],
        },
      ],
    });
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByText('내용을 잘 읽었어요')).toBeVisible();
  await expect(page.getByText('1곳만 확인해주세요')).toHaveCount(0);
  await expect(page.getByText('확인 권장', { exact: true })).toHaveCount(1);
  await expect(page.getByText('원본 미리보기를 불러오지 못했어요')).toBeVisible();
  await expect(page.getByRole('img', { name: '등록한 약봉투 원본' })).toHaveCount(0);

  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21',
  );

  expect(patches).toHaveLength(1);
  expectAuthenticated(images);
  expectAuthenticated(patches);
});

test('이미 완료되었거나 실패한 문서 OCR 상태를 기존 화면으로 보여준다', async ({ page }) => {
  await authenticate(page);
  let failed = false;
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(
        route,
        failed
          ? { batchId: 'b_mock_9f21', ocrStatus: 'failed', errorCode: 'EXTRACTION_FAILED' }
          : { ...readyOcrResult, batchId: 'b_mock_9f21', ocrStatus: 'complete' },
      );
      return;
    }
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21/image') {
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    await route.continue();
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByText('이미 등록된 약봉투예요')).toBeVisible();
  await expect(page.getByRole('button', { name: '저장 완료' })).toBeVisible();

  failed = true;
  await page.goto('/dev/ocr-review');
  const failureDialog = page.getByRole('dialog');
  await expect(failureDialog.getByRole('heading', { name: '문서를 읽지 못했어요' })).toBeVisible();
  await expect(failureDialog.getByRole('button', { name: '다시 촬영' })).toBeVisible();
  await expect(failureDialog.getByRole('button', { name: '그대로 직접 입력' })).toBeVisible();
});
