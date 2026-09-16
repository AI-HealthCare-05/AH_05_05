import { readFileSync } from 'node:fs';
import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const ACCESS_TOKEN = 'e2e-document-token';
const DOCUMENT_ID = 501;
const OCR_URL = `/api/v1/ocr/jobs/${DOCUMENT_ID}`;
const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8+QAAAABJRU5ErkJggg==',
  'base64',
);
const MEDICATION_CAPTURE_GUIDE_PNG = readFileSync(
  new URL('../../public/images/medication-capture-guide.png', import.meta.url),
);

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

interface CapturedRequest {
  method: string;
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
    hospitalName: { value: '송도센트럴이비인후과의원', confidence: 'high' },
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
      timesPerDay: 1,
      days: 7,
      confidence: 'high',
    },
    {
      tempId: 'm4',
      name: ' 파모티딘 원문 ',
      timesPerDay: 1,
      days: 7,
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
    method: request.method(),
    url: request.url(),
    headers: request.headers(),
    body: request.postDataBuffer()?.toString('utf8') ?? '',
    // Polling intervals must not change when the host wall clock is corrected.
    requestedAt: performance.now(),
  };
}

async function authenticate(page: Page) {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'ocr-e2e@example.com');
  }, ACCESS_TOKEN);
}

async function stubNonMedicationHomeData(page: Page) {
  // 홈의 부가 요청이 실제 서버로 새어 fixture 계정을 로그아웃시키지 않게 합니다.
  await page.route('**/api/v1/user/challenges', route =>
    fulfillJson(route, { items: [], total_count: 0 }),
  );
  await page.route('**/api/v1/display/med/nutr/rank*', route =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', route =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
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

test('새로고침한 OCR 검토는 사진을 다시 요청하지 않고 결과만 보여준다', async ({ page }) => {
  await authenticate(page);
  const imageRequests: string[] = [];
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === OCR_URL) {
      await fulfillJson(route, { ...readyOcrResult, batchId: String(DOCUMENT_ID) });
      return;
    }
    if (request.method() === 'GET' && (path.endsWith('/image') || path.endsWith('/processed-image'))) {
      imageRequests.push(path);
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    await route.continue();
  });

  await page.goto(`/ocr-review?batchId=${DOCUMENT_ID}`);

  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByText('새로고침하면 사진 미리보기를 다시 불러올 수 없어요.', { exact: true })).toBeVisible();
  expect(imageRequests).toEqual([]);
});

test('새 사진 세션은 원본 File과 전처리본을 받은 뒤에만 사진 삭제를 확인한다', async ({ page }) => {
  await authenticate(page);
  let processedRequests = 0;
  let originalRequests = 0;
  let releaseRequests = 0;
  let releaseProcessed!: () => void;
  const processedPending = new Promise<void>((resolve) => { releaseProcessed = resolve; });
  await page.route('**/api/v1/ocr', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { batchId: 'upload-batch-501', documentIds: [DOCUMENT_ID], ocrStatus: 'queued' });
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === OCR_URL) {
      await fulfillJson(route, { ...readyOcrResult, batchId: String(DOCUMENT_ID) });
      return;
    }
    if (request.method() === 'GET' && path === `${OCR_URL}/processed-image`) {
      processedRequests += 1;
      await processedPending;
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    if (request.method() === 'GET' && path === `${OCR_URL}/image`) {
      originalRequests += 1;
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    if (request.method() === 'POST' && path === `${OCR_URL}/release-images`) {
      releaseRequests += 1;
      expect(request.postData()).toBeNull();
      await route.fulfill({ status: 204 });
      return;
    }
    await route.continue();
  });

  await page.goto('/document-upload');
  await selectGalleryPng(page);
  await page.getByRole('button', { name: '등록하기', exact: true }).click();
  await expect.poll(() => processedRequests).toBe(1);
  expect(releaseRequests).toBe(0);
  expect(originalRequests).toBe(0);
  expect(await page.evaluate(() => (window.history.state?.usr as { file?: unknown } | undefined)?.file)).toBeUndefined();

  releaseProcessed();
  await expect(page.getByRole('img', { name: '약봉투 미리보기' })).toBeVisible();
  await expect.poll(() => releaseRequests).toBe(1);
  expect(originalRequests).toBe(0);

  await page.reload();
  await expect(page.getByText('새로고침하면 사진 미리보기를 다시 불러올 수 없어요.', { exact: true })).toBeVisible();
  await expect(page.getByRole('img', { name: '약봉투 미리보기' })).toHaveCount(0);
  expect(processedRequests).toBe(1);
  expect(releaseRequests).toBe(1);
});

test('전처리본 수신 실패는 사진 삭제 확인을 보내지 않는다', async ({ page }) => {
  await authenticate(page);
  let originalRequests = 0;
  let releaseRequests = 0;
  await page.route('**/api/v1/ocr', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { batchId: 'upload-batch-501', documentIds: [DOCUMENT_ID], ocrStatus: 'queued' });
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === OCR_URL) {
      await fulfillJson(route, { ...readyOcrResult, batchId: String(DOCUMENT_ID) });
      return;
    }
    if (request.method() === 'GET' && path === `${OCR_URL}/processed-image`) {
      await fulfillJson(route, { code: 'TEMPORARY', message: 'temporary failure' }, 503);
      return;
    }
    if (request.method() === 'GET' && path === `${OCR_URL}/image`) {
      originalRequests += 1;
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    if (request.method() === 'POST' && path === `${OCR_URL}/release-images`) {
      releaseRequests += 1;
      await route.fulfill({ status: 204 });
      return;
    }
    await route.continue();
  });

  await page.goto('/document-upload');
  await selectGalleryPng(page);
  await page.getByRole('button', { name: '등록하기', exact: true }).click();

  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByText('새로고침하면 사진 미리보기를 다시 불러올 수 없어요.', { exact: true })).toBeVisible();
  expect(releaseRequests).toBe(0);
  expect(originalRequests).toBe(0);
});

for (const width of [375, 1280]) {
  test(`OCR 문서 재등록은 기존 작업 취소 완료 후 등록 화면으로 이동한다 (${width})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate(page);
    await page.route(`**${OCR_URL}`, (route) => fulfillJson(route, readyOcrResult));
    await page.route(`**${OCR_URL}/*image`, (route) => route.fulfill({ status: 404 }));
    let finishCancel: (() => void) | undefined;
    let cancelCount = 0;
    await page.route(`**${OCR_URL}/cancel`, async (route) => {
      expect(route.request().method()).toBe('POST');
      expect(route.request().headers().authorization).toBe(`Bearer ${ACCESS_TOKEN}`);
      cancelCount += 1;
      await new Promise<void>((resolve) => { finishCancel = resolve; });
      await route.fulfill({ status: 204 });
    });
    await page.goto(`/dev/ocr-review?batchId=${DOCUMENT_ID}`);
    await page.getByRole('button', { name: '문서 다시 등록', exact: true }).click();
    await expect.poll(() => cancelCount).toBe(1);
    await expect(page).toHaveURL(/ocr-review/);
    await expect(page.getByRole('button', { name: '취소 중...', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true })).toBeDisabled();
    await page.screenshot({ path: testInfo.outputPath('cancel-pending.png'), fullPage: true });
    finishCancel!();
    await expect(page).toHaveURL(/document-upload/);
    expect(cancelCount).toBe(1);
  });
}

test('OCR 문서 재등록 취소 요청이 실패하면 검토 화면에서 다시 시도할 수 있다', async ({ page }) => {
  await authenticate(page);
  await page.route(`**${OCR_URL}`, (route) => fulfillJson(route, readyOcrResult));
  await page.route(`**${OCR_URL}/*image`, (route) => route.fulfill({ status: 404 }));
  let cancelCount = 0;
  await page.route(`**${OCR_URL}/cancel`, async (route) => {
    cancelCount += 1;
    if (cancelCount === 1) await fulfillJson(route, { detail: 'temporary failure' }, 503);
    else await route.fulfill({ status: 204 });
  });
  await page.goto(`/dev/ocr-review?batchId=${DOCUMENT_ID}`);
  await page.getByRole('button', { name: '문서 다시 등록', exact: true }).click();
  await expect(page.getByText('기존 OCR 작업을 취소하지 못했어요. 다시 시도해주세요.', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/ocr-review/);
  await page.getByRole('button', { name: '문서 다시 등록', exact: true }).click();
  await expect(page).toHaveURL(/document-upload/);
  expect(cancelCount).toBe(2);
});

test('READY 검토 나가기는 취소가 완료될 때까지 홈으로 이동하지 않는다', async ({ page }) => {
  await authenticate(page);
  let cancelCount = 0;
  let releaseCancel!: () => void;
  const cancelPending = new Promise<void>((resolve) => {
    releaseCancel = resolve;
  });
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(route, { ...readyOcrResult, batchId: 'b_mock_9f21' });
      return;
    }
    if (request.method() === 'POST' && path === '/api/v1/ocr/jobs/b_mock_9f21/cancel') {
      cancelCount += 1;
      await cancelPending;
      await route.fulfill({ status: 204 });
      return;
    }
    if (request.method() === 'GET' && path.includes('/image')) {
      await route.fulfill({ status: 404 });
      return;
    }
    await route.continue();
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  const exitDialog = page.getByRole('dialog', { name: '설정을 취소하고 나갈까요?' });
  const leave = exitDialog.getByRole('button', { name: '나가기', exact: true });
  await leave.click();
  await expect.poll(() => cancelCount).toBe(1);
  await expect(page).toHaveURL(/\/ocr-review/);
  await expect(exitDialog.getByRole('button', { name: '취소 중...', exact: true })).toBeDisabled();
  expect(cancelCount).toBe(1);

  releaseCancel();
  await expect(page).toHaveURL('/home');
  expect(cancelCount).toBe(1);
});

test('READY 검토 나가기 취소 실패는 화면에 머물고 다시 시도할 수 있다', async ({ page }) => {
  await authenticate(page);
  let cancelCount = 0;
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(route, { ...readyOcrResult, batchId: 'b_mock_9f21' });
      return;
    }
    if (request.method() === 'POST' && path === '/api/v1/ocr/jobs/b_mock_9f21/cancel') {
      cancelCount += 1;
      if (cancelCount === 1) {
        await fulfillJson(route, { code: 'temporary' }, 503);
      } else {
        await route.fulfill({ status: 204 });
      }
      return;
    }
    if (request.method() === 'GET' && path.includes('/image')) {
      await route.fulfill({ status: 404 });
      return;
    }
    await route.continue();
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  const exitDialog = page.getByRole('dialog', { name: '설정을 취소하고 나갈까요?' });
  const leave = exitDialog.getByRole('button', { name: '나가기', exact: true });
  await leave.click();
  await expect(page.getByText('기존 OCR 작업을 취소하지 못했어요. 다시 시도해주세요.')).toBeVisible();
  await expect(page).toHaveURL(/\/ocr-review/);
  await expect(leave).toBeEnabled();
  await leave.click();
  await expect(page).toHaveURL('/home');
  expect(cancelCount).toBe(2);
});

test('COMPLETE 등록 수정 나가기는 OCR 취소 요청 없이 홈으로 이동한다', async ({ page }) => {
  await authenticate(page);
  let cancelCount = 0;
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(route, { ...readyOcrResult, batchId: 'b_mock_9f21', ocrStatus: 'complete' });
      return;
    }
    if (request.method() === 'POST' && path === '/api/v1/ocr/jobs/b_mock_9f21/cancel') {
      cancelCount += 1;
      await route.fulfill({ status: 204 });
      return;
    }
    if (request.method() === 'GET' && path.includes('/image')) {
      await route.fulfill({ status: 404 });
      return;
    }
    await route.continue();
  });

  await page.goto('/ocr-review?batchId=b_mock_9f21&recordId=315&mode=registration-edit&flow=registration');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await page.getByRole('dialog', { name: '설정을 취소하고 나갈까요?' })
    .getByRole('button', { name: '나가기', exact: true })
    .click();
  await expect(page).toHaveURL('/home');
  expect(cancelCount).toBe(0);
});

async function interceptDefaultNotifySettings(page: Page) {
  await page.route('**/api/v1/me/settings', async (route) => {
    await fulfillJson(route, {
      notifyMedication: false,
      notifySupplement: false,
      notifySchedule: false,
      notifyConsentedAt: null,
      morningMedicationTime: '08:00:00',
      lunchMedicationTime: '13:00:00',
      eveningMedicationTime: '19:00:00',
      bedtimeMedicationTime: '22:00:00',
    });
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

    if (request.method() === 'POST' && path === `${OCR_URL}/release-images`) {
      await route.fulfill({ status: 204 });
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

for (const width of [375, 1280]) {
test(`OCR synthetic fixture 미리보기 전환과 선명한 닫기·한 번 클릭 닫기 (${width})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 900 });
  await authenticate(page);
  const requestedImages: string[] = [];

  await page.route('**/api/v1/ocr', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { batchId: 'upload-batch-501', documentIds: [DOCUMENT_ID], ocrStatus: 'queued' });
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === OCR_URL) {
      await fulfillJson(route, { ...readyOcrResult, batchId: String(DOCUMENT_ID) });
      return;
    }
    if (
      request.method() === 'GET' &&
      (path === `${OCR_URL}/processed-image` || path === `${OCR_URL}/image`)
    ) {
      requestedImages.push(path);
      await route.fulfill({ status: 200, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="600"><rect width="900" height="600" fill="#eee8db"/><rect x="100" y="80" width="700" height="440" fill="white"/><text x="160" y="170" font-size="36">OCR preview sample</text><path d="M160 230h580M160 300h580M160 370h580M160 440h350" stroke="#b7c4c1" stroke-width="12"/></svg>' });
      return;
    }
    if (request.method() === 'POST' && path === `${OCR_URL}/release-images`) {
      await route.fulfill({ status: 204 });
      return;
    }
    await route.continue();
  });

  await page.goto('/document-upload');
  await selectGalleryPng(page);
  await page.getByRole('button', { name: '등록하기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();

  const preview = page.getByRole('img', { name: '약봉투 미리보기' });
  await expect(preview).toBeVisible();
  await expect(page.getByText('전처리한 약봉투', { exact: true })).toHaveCount(0);
  expect(await preview.evaluate((image) => getComputedStyle(image).objectFit)).toBe('contain');
  const previewBox = await preview.boundingBox();
  expect(previewBox).not.toBeNull();
  expect(previewBox!.height).toBeGreaterThanOrEqual(287);
  expect(previewBox!.height).toBeLessThanOrEqual(288);

  await page.getByRole('button', { name: '약봉투 크게 보기' }).click();
  const viewer = page.getByRole('dialog');
  const enlarged = viewer.getByRole('img', { name: '확대한 약봉투' });
  await expect(enlarged).toBeVisible();
  const processedSrc = await enlarged.getAttribute('src');
  expect(processedSrc).toMatch(/^blob:/);
  await expect(viewer.getByRole('button', { name: '선명하게 보기' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.screenshot({ path: testInfo.outputPath(`image-viewer-${width}.png`) });

  await viewer.getByRole('button', { name: '원본 보기' }).click();
  const original = viewer.getByRole('img', { name: '확대한 약봉투 원본' });
  await expect(original).toBeVisible();
  await expect(original).toHaveAttribute('src', /^blob:/);
  await expect(original).not.toHaveAttribute(
    'src',
    processedSrc ?? '',
  );
  await expect.poll(async () => original.evaluate((image) => {
    const dialog = image.closest('[role="dialog"]');
    const overlay = document.querySelector<HTMLElement>('[data-slot="dialog-overlay"]');
    return image.complete && image.naturalWidth > 0 && image.naturalHeight > 0 &&
      getComputedStyle(image).opacity === '1' &&
      getComputedStyle(dialog ?? image).opacity === '1' &&
      getComputedStyle(overlay ?? image).opacity === '1';
  })).toBe(true);
  expect(requestedImages).toEqual([
    `${OCR_URL}/processed-image`,
  ]);
  const close = viewer.getByRole('button', { name: '닫기', exact: true });
  const closeBox = await close.boundingBox();
  expect.soft(closeBox!.width).toBeGreaterThanOrEqual(48);
  expect.soft(closeBox!.height).toBeGreaterThanOrEqual(48);
  await viewer.getByRole('img', { name: '확대한 약봉투 원본' }).click();
  await expect(viewer).toBeVisible();
  await close.click();
  await expect(viewer).toBeHidden();
  await page.getByRole('button', { name: '약봉투 크게 보기' }).click();
  await viewer.getByRole('button', { name: '선명하게 보기' }).click();
  await expect(viewer).toBeVisible();
  await viewer.getByRole('img', { name: '확대한 약봉투' }).click();
  await expect(viewer).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(viewer).toBeHidden();
});
}

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
  await expect(page.getByLabel('병원명')).toHaveValue('송도센트럴이비인후과의원');
  await expect(page.getByLabel('병원명')).toHaveAttribute('maxlength', '255');
  await expect(page.getByLabel('복약 별칭')).toHaveValue('송도센트럴이비인후과의원');
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
  ).toBe('0px');

  await days.fill('999');
  await expect(days).toHaveValue('');
  await days.fill('365');
  await expect(days).toHaveValue('365');
});

test('직접 추가는 복용 일수와 횟수를 요구하고 필요 시를 허용한다', async ({ page }) => {
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
  await page.getByRole('button', { name: '직접 추가', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약 추가' });
  const save = dialog.getByRole('button', { name: '저장', exact: true });

  await dialog.getByLabel('약품명').fill('직접 추가 약');
  await expect(save).toBeDisabled();
  await dialog.getByLabel('복용 일수').fill('7');
  await expect(save).toBeDisabled();

  await dialog.getByRole('combobox').click();
  await page.getByRole('option', { name: '6회', exact: true }).click();
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByRole('article', { name: '직접 추가 약', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '직접 추가 약 수정', exact: true }).click();
  const editDialog = page.getByRole('dialog', { name: '직접 추가 약 수정' });
  await editDialog.getByRole('combobox').click();
  await page.getByRole('option', { name: '필요 시', exact: true }).click();
  await expect(editDialog.getByRole('button', { name: '저장', exact: true })).toBeEnabled();
});

for (const width of [375, 1280]) {
  test(`OCR 미추출 복용 정보는 낮은 신뢰도 확인으로도 확정할 수 없다 (${width}px)`, async ({ page }, testInfo) => {
    await authenticate(page);
    let patchCount = 0;
    await page.route('**/api/v1/ocr/**', async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (request.method() === 'PATCH' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
        patchCount += 1;
        await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
        return;
      }
      if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
        await fulfillJson(route, {
          batchId: 'b_mock_9f21',
          ocrStatus: 'ready_for_review',
          documentImageUrl: '',
          fields: {
            dispensedDate: { value: '2026-08-22', confidence: 'high' },
          },
          medications: [
            { tempId: 'missing-intake', name: '미추출 복용약', confidence: 'low' },
          ],
          lowConfidenceCount: 1,
        });
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

    await page.setViewportSize({ width, height: 900 });
    await page.goto('/ocr-review?batchId=b_mock_9f21');

    await expect(page.getByRole('alert')).toContainText('복용 일수와 1일 복용 횟수를 모두 입력해주세요.');
    await expect(page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true })).toBeDisabled();
    await expect(page.getByRole('dialog', { name: '확인이 필요한 항목을 모두 보셨나요?' })).toHaveCount(0);
    expect(patchCount).toBe(0);
    await page.screenshot({ path: testInfo.outputPath(`ocr-missing-intake-${width}.png`), fullPage: true });
  });
}

test('OCR 결과를 확정하면 해당 복약 시간 설정 화면으로 이동한다', async ({ page }) => {
  await authenticate(page);
  await interceptDefaultNotifySettings(page);
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
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/*image', async (route) => {
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
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21&flow=registration',
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

  await expect(page.getByText('세프디니르건조시럽', { exact: true })).toBeVisible();
  await expect(page.getByText('암브록솔시럽', { exact: true })).toBeVisible();
  await expect(page.getByText('슈도에페드린시럽', { exact: true })).toBeVisible();
  await expect(page.getByText('프로바이오틱스분말', { exact: true })).toBeVisible();

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

for (const backMethod of ['화살표', '브라우저'] as const) {
test(`복약 시간 설정의 ${backMethod} 뒤로가기는 로딩 없이 수정 가능한 OCR 결과로 돌아간다`, async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: backMethod === '브라우저' ? 375 : 1280, height: 900 });
  const goBack = async () => {
    if (backMethod === '브라우저') await page.goBack();
    else await page.getByRole('button', { name: '뒤로 가기' }).click();
  };
  await authenticate(page);
  await interceptDefaultNotifySettings(page);
  let confirmed = false;
  const ocrRequests: Array<{ method: string; url: string }> = [];
  const patchPayloads: Array<Record<string, unknown>> = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/ocr' || path === '/api/v1/ocr/jobs/b_mock_9f21') {
      ocrRequests.push({ method: request.method(), url: request.url() });
    }
  });

  await page.route('**/api/v1/ocr/jobs/b_mock_9f21*', async (route) => {
    if (route.request().method() === 'PATCH') {
      patchPayloads.push(route.request().postDataJSON() as Record<string, unknown>);
      confirmed = true;
      await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      return;
    }
    await fulfillJson(route, {
      ...readyOcrResult,
      batchId: 'b_mock_9f21',
      ocrStatus: confirmed ? 'complete' : 'ready_for_review',
      fields: {
        hospitalName: { value: '연세의원', confidence: 'low' },
        dispensedDate: { value: '2026-08-22', confidence: 'low' },
      },
      medications: readyOcrResult.medications.map((medication) => ({
        ...medication,
        confidence: 'high',
      })),
      lowConfidenceCount: 0,
    });
  });
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/*image', async (route) => {
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
  await expect(page.getByLabel('복약 별칭')).toHaveValue('연세의원');
  await page.getByLabel('복약 별칭').fill('사용자 별칭');
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog', { name: '확인이 필요한 항목을 모두 보셨나요?' })
    .getByRole('button', { name: '확인 후 저장', exact: true })
    .click();
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21&flow=registration',
  );
  await expect(page.getByText('3 / 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '약마다 먹는 시간을 확인해주세요' })).toBeVisible();
  const ocrGetCountBeforeBack = ocrRequests.filter((request) => request.method === 'GET').length;
  await goBack();

  await expect(page).toHaveURL(
    '/ocr-review?batchId=b_mock_9f21&recordId=315&mode=registration-edit&flow=registration',
  );
  await expect(page.getByRole('heading', { name: '약봉투를 읽고 있어요' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible();
  await expect(page.getByLabel('병원명')).toHaveValue('연세의원');
  const hospitalNameHeader = page.locator('label[for="hospitalName"]').locator('..');
  await expect(hospitalNameHeader.getByText('확인 필요', { exact: true })).toBeVisible();
  await expect(page.getByLabel('조제일')).toBeEditable();
  await expect(page.getByLabel('복약 별칭')).toHaveValue('사용자 별칭');
  await expect(page.getByRole('button', { name: '직접 추가', exact: true })).toBeVisible();
  await expect(page.getByText('이미 등록된 약봉투예요')).toHaveCount(0);
  const dispensedDateHeader = page.locator('label[for="dispensedDate"]').locator('..');
  await expect(dispensedDateHeader.getByText('확인 필요', { exact: true })).toBeVisible();
  await page.getByLabel('조제일').fill('2026-08-21');
  await page.getByLabel('병원명').fill('연세의원 수정');
  await expect(hospitalNameHeader.getByText('확인 필요', { exact: true })).toHaveCount(0);
  await expect(dispensedDateHeader.getByText('확인 필요', { exact: true })).toHaveCount(0);
  expect(ocrRequests.filter((request) => request.method === 'GET')).toHaveLength(
    ocrGetCountBeforeBack,
  );

  expect(patchPayloads).toHaveLength(1);
  await page.screenshot({ path: testInfo.outputPath('ocr-back-editable.png'), fullPage: true });
  await page.getByRole('button', { name: '셀레콕시브 수정', exact: true }).click();
  const editDialog = page.getByRole('dialog');
  await editDialog.getByLabel('약품명').fill('셀레콕시브 수정');
  await editDialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('article', { name: '셀레콕시브 수정', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  const reviewDialog = page.getByRole('dialog', { name: '확인이 필요한 항목을 모두 보셨나요?' });
  if (await reviewDialog.isVisible()) {
    await reviewDialog.getByRole('button', { name: '확인 후 저장', exact: true }).click();
  }
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21&flow=registration',
  );
  expect(patchPayloads).toHaveLength(2);
  expect(patchPayloads[1]).toMatchObject({
    hospitalName: '연세의원 수정',
    alias: '사용자 별칭',
  });
  await goBack();
  await expect(page.getByLabel('병원명')).toHaveValue('연세의원 수정');
  await expect(page.getByLabel('복약 별칭')).toHaveValue('사용자 별칭');
  await page.getByLabel('복약 별칭').fill('');
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  const finalReviewDialog = page.getByRole('dialog', { name: '확인이 필요한 항목을 모두 보셨나요?' });
  if (await finalReviewDialog.isVisible()) {
    await finalReviewDialog.getByRole('button', { name: '확인 후 저장', exact: true }).click();
  }
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21&flow=registration',
  );
  expect(patchPayloads).toHaveLength(3);
  expect(patchPayloads[2].alias).toBeNull();
  await goBack();
  await expect(page.getByLabel('복약 별칭')).toHaveValue('');
  const patches = ocrRequests.filter((request) => request.method === 'PATCH');
  expect(patches).toHaveLength(3);
  expect(new URL(patches[2].url).searchParams.get('registrationEdit')).toBe('true');
  expect(ocrRequests.filter((request) => request.method === 'POST')).toHaveLength(0);
});
}

test('등록 수정 URL 직접 진입은 재판독 연출 없이 완료 결과를 불러와 편집한다', async ({
  page,
}) => {
  await authenticate(page);
  const imageRequests: string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (
      path === '/api/v1/ocr/jobs/b_mock_9f21/image' ||
      path === '/api/v1/ocr/jobs/b_mock_9f21/processed-image'
    ) {
      imageRequests.push(path);
    }
  });
  let releaseResult!: () => void;
  const resultGate = new Promise<void>((resolve) => {
    releaseResult = resolve;
  });
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21', async (route) => {
    await resultGate;
    await fulfillJson(route, {
      ...readyOcrResult,
      batchId: 'b_mock_9f21',
      ocrStatus: 'complete',
    });
  });
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/*image', async (route) => {
    await route.fulfill({ status: 404 });
  });

  await page.goto(
    '/ocr-review?batchId=b_mock_9f21&recordId=315&mode=registration-edit&flow=registration',
  );
  await expect(page.getByRole('heading', { name: '약봉투를 읽고 있어요' })).toHaveCount(0);
  await expect(page.getByRole('status')).toHaveText('저장한 정보를 불러오는 중...');

  releaseResult();
  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible();
  await expect(page.getByLabel('조제일')).toBeEditable();
  await expect(page.getByRole('img', { name: '약봉투 미리보기' })).toHaveCount(0);
  expect(imageRequests).toEqual([]);
});

for (const width of [375, 1280]) {
test(`OCR 2페이지 뒤로가기는 설정 취소를 확인하고 홈으로 나간다 (${width})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 900 });
  const mutations: string[] = [];
  page.on('request', (request) => {
    if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(request.method())) {
      mutations.push(request.method());
    }
  });
  await authenticate(page);
  await interceptDefaultNotifySettings(page);
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
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/*image', async (route) => {
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
  await expect(page.getByRole('dialog', { name: '확인이 필요한 항목을 모두 보셨나요?' })).toHaveCount(0);

  await page.getByLabel('복용 시작 날짜').fill('2026-08-20');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기' }).click();

  const exitDialog = page.getByRole('dialog', { name: '설정을 취소하고 나갈까요?' });
  await expect(exitDialog).toBeVisible();
  await expect(exitDialog).toContainText('이미 저장된 약 정보는 유지돼요.');
  await page.keyboard.press('Escape');
  await expect(exitDialog).toBeHidden();
  await page.getByLabel('복약 별칭').fill('나가기 취소 후 유지할 별칭');
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await exitDialog.getByRole('button', { name: '계속 설정', exact: true }).click();
  await expect(exitDialog).toBeHidden();
  await expect(page.getByLabel('복약 별칭')).toHaveValue('나가기 취소 후 유지할 별칭');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByText('2 / 5', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await page.screenshot({ path: testInfo.outputPath('ocr-exit-confirm.png') });
  await exitDialog.getByRole('button', { name: '나가기', exact: true }).click();
  await expect(page).toHaveURL('/home');
  expect(mutations).toEqual(['PATCH']);
});
}

for (const width of [375, 1280]) {
test(`등록 시간 초과 선택은 버튼을 비활성화하지 않고 해당 약 아래 안내한다 (${width})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 1000 });
  await authenticate(page);
  await interceptDocumentRegistration(page);
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, { start: null, mealTimes: null, medications: template04ScheduleMedications });
  });
  await page.goto('/medication-schedule?recordId=314&ocrJobId=b_mock_9f21&flow=registration');
  const morning = page.getByRole('button', { name: '슈도에페드린시럽 아침약' });
  const evening = page.getByRole('button', { name: '슈도에페드린시럽 저녁약' });
  const confirm = page.getByRole('button', { name: '확인', exact: true });
  await expect(page.getByText('하루 2회', { exact: true })).toHaveCount(3);
  const card = page.getByRole('group', { name: '슈도에페드린시럽', exact: true });
  const warning = card.getByRole('alert');
  await expect(evening).toBeEnabled();
  await expect(warning).toHaveCount(0);
  await evening.click();
  await expect(evening).toHaveAttribute('aria-pressed', 'false');
  await expect(morning).toHaveAttribute('aria-pressed', 'true');
  await expect(warning).toHaveText('하루 2회만 선택할 수 있어요. 선택한 시간을 취소한 뒤 다른 시간을 선택해주세요.');
  await expect(page.getByRole('alert')).toHaveCount(1);
  await page.screenshot({ path: testInfo.outputPath('slot-limit-warning.png'), fullPage: true });
  await morning.click();
  await expect(warning).toHaveCount(0);
  await expect(evening).toBeEnabled();
  await expect(confirm).toBeDisabled();
  await evening.click();
  await expect(morning).toBeEnabled();
  await expect(evening).toHaveAttribute('aria-pressed', 'true');
  await expect(morning).toHaveAttribute('aria-pressed', 'false');
  await expect(confirm).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('slot-limits.png'), fullPage: true });
});
}

test('아직 안 먹었어요는 복용 완료를 만들지 않고 오늘 첫 사용 슬롯부터 기록한다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-09-03T12:00:00+09:00'));
  await authenticate(page);
  const trace = await interceptDocumentRegistration(page);
  const doseWrites: CapturedRequest[] = [];
  await page.route('**/api/v1/medications/doses**', async (route) => {
    if (route.request().method() === 'POST') doseWrites.push(capture(route));
    await route.continue();
  });

  await page.goto(
    '/medication-schedule?recordId=314&ocrJobId=b_mock_9f21&flow=registration',
  );
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '아직 안 먹었어요' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  await expect(page.getByText('첫 복용 아직 복용 전')).toBeVisible();
  const saveRequest = trace.scheduleRequests.find((request) => request.method === 'PUT');
  expect(saveRequest).toBeDefined();
  expect(JSON.parse(saveRequest!.body)).toMatchObject({
    start: { date: '2026-09-03', slot: 'morning' },
  });
  expect(doseWrites).toHaveLength(0);
});

test('실제 첫 복용 선택은 일정 저장 뒤 해당 날짜·시간대의 복용 기록을 저장한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-03T12:00:00+09:00'));
  await authenticate(page);
  const trace = await interceptDocumentRegistration(page);
  const doseWrites: CapturedRequest[] = [];
  await page.route('**/api/v1/medications/doses', async (route) => {
    if (route.request().method() === 'POST') {
      doseWrites.push(capture(route));
      await fulfillJson(route, {
        date: '2026-09-02',
        slot: 'evening',
        taken: true,
        recordId: 314,
      });
      return;
    }
    await route.continue();
  });

  await page.goto('/medication-schedule?recordId=314&ocrJobId=b_mock_9f21&flow=registration');
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByLabel('복용 시작 날짜').fill('2026-09-02');
  await page.getByRole('button', { name: '시작 저녁약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  const scheduleSave = trace.scheduleRequests.find((request) => request.method === 'PUT');
  expect(scheduleSave).toBeDefined();
  expect(doseWrites).toHaveLength(1);
  expect(doseWrites[0].requestedAt).toBeGreaterThan(scheduleSave!.requestedAt);
  expect(JSON.parse(doseWrites[0].body)).toEqual({
    date: '2026-09-02',
    slot: 'evening',
    taken: true,
    recordId: 314,
  });
});

test('dose 허용 범위 밖 첫 복용일은 일정 저장 전에 막고 365일 전 경계는 허용한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-03T12:00:00+09:00'));
  await authenticate(page);
  const trace = await interceptDocumentRegistration(page);
  const doseWrites: CapturedRequest[] = [];
  await page.route('**/api/v1/medications/doses', async (route) => {
    if (route.request().method() === 'POST') {
      doseWrites.push(capture(route));
      await fulfillJson(route, {
        date: '2025-09-03',
        slot: 'evening',
        taken: true,
        recordId: 314,
      });
      return;
    }
    await route.continue();
  });

  await page.goto('/medication-schedule?recordId=314&ocrJobId=b_mock_9f21&flow=registration');
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByLabel('복용 시작 날짜').fill('2025-09-02');
  await page.getByRole('button', { name: '시작 저녁약' }).click();

  await expect(page.getByRole('alert')).toContainText(
    '첫 복용 날짜는 오늘 기준 최근 365일 이내로 골라주세요.',
  );
  await expect(page.getByRole('button', { name: '확인', exact: true })).toBeDisabled();
  await expect.poll(() => trace.scheduleRequests.filter((request) => request.method === 'PUT')).toHaveLength(0);

  await page.getByLabel('복용 시작 날짜').fill('2025-09-03');
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '확인', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  expect(trace.scheduleRequests.filter((request) => request.method === 'PUT')).toHaveLength(1);
  expect(doseWrites).toHaveLength(1);
  expect(JSON.parse(doseWrites[0].body)).toEqual({
    date: '2025-09-03',
    slot: 'evening',
    taken: true,
    recordId: 314,
  });
});

test('첫 복용 기록 저장 뒤 최종 not_taken 선택은 기존 기록을 되돌린다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-03T12:00:00+09:00'));
  await authenticate(page);
  const trace = await interceptDocumentRegistration(page);
  const doseWrites: CapturedRequest[] = [];
  await page.route('**/api/v1/medications/doses', async (route) => {
    if (route.request().method() === 'POST') {
      doseWrites.push(capture(route));
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      await fulfillJson(route, payload);
      return;
    }
    await route.continue();
  });

  let settingsAttempts = 0;
  await page.unroute('**/api/v1/me/settings');
  await page.route('**/api/v1/me/settings', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, {
        notifyMedication: false,
        notifySupplement: false,
        notifySchedule: false,
        notifyConsentedAt: null,
        morningMedicationTime: '08:00:00',
        lunchMedicationTime: '13:00:00',
        eveningMedicationTime: '19:00:00',
        bedtimeMedicationTime: '22:00:00',
      });
      return;
    }
    if (route.request().method() === 'PATCH') {
      settingsAttempts += 1;
      if (settingsAttempts === 1) {
        await fulfillJson(route, { code: 'SETTINGS_SAVE_FAILED', message: '알림 설정을 저장하지 못했어요.' }, 503);
        return;
      }
      await fulfillJson(route, {
        notifyMedication: false,
        notifySupplement: false,
        notifySchedule: false,
        notifyConsentedAt: new Date().toISOString(),
        morningMedicationTime: '08:00:00',
        lunchMedicationTime: '13:00:00',
        eveningMedicationTime: '19:00:00',
        bedtimeMedicationTime: '22:00:00',
      });
      return;
    }
    await route.continue();
  });

  await page.goto('/medication-schedule?recordId=314&ocrJobId=b_mock_9f21&flow=registration');
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '시작 아침약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  const saveError = page.getByRole('alert');
  await expect(saveError).toContainText('알림 설정을 저장하지 못했어요.');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await page.getByRole('button', { name: '아직 안 먹었어요' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  expect(settingsAttempts).toBe(2);
  expect(trace.scheduleRequests.filter((request) => request.method === 'PUT')).toHaveLength(1);
  expect(doseWrites.map((request) => JSON.parse(request.body))).toEqual([
    { date: '2026-09-03', slot: 'morning', taken: true, recordId: 314 },
    { date: '2026-09-03', slot: 'morning', taken: false, recordId: 314 },
  ]);
});

test('복용 기록만 실패하면 일정은 다시 저장하지 않고 복용 기록만 재시도한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-03T12:00:00+09:00'));
  await authenticate(page);
  const trace = await interceptDocumentRegistration(page);
  let doseAttempts = 0;
  await page.route('**/api/v1/medications/doses', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    doseAttempts += 1;
    if (doseAttempts === 1) {
      await fulfillJson(route, { code: 'DOSE_SAVE_FAILED', message: '복용 기록을 저장하지 못했어요.' }, 503);
      return;
    }
    await fulfillJson(route, {
      date: '2026-09-02',
      slot: 'evening',
      taken: true,
      recordId: 314,
    });
  });

  await page.goto('/medication-schedule?recordId=314&ocrJobId=b_mock_9f21&flow=registration');
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByLabel('복용 시작 날짜').fill('2026-09-02');
  await page.getByRole('button', { name: '시작 저녁약' }).click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '등록 완료', exact: true }).click();

  const saveError = page.getByRole('alert');
  await expect(saveError).toContainText('복용 기록을 저장하지 못했어요.');
  const retry = saveError.getByRole('button', { name: '다시 시도', exact: true });
  await expect(retry).toBeVisible();
  await retry.click();

  await expect(page.getByRole('heading', { name: '약 등록을 완료했어요' })).toBeVisible();
  expect(doseAttempts).toBe(2);
  expect(trace.scheduleRequests.filter((request) => request.method === 'PUT')).toHaveLength(1);
});

function expectAuthenticated(requests: CapturedRequest[]) {
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every((request) => request.headers.authorization === `Bearer ${ACCESS_TOKEN}`)).toBe(
    true,
  );
}

test('복약안내문 촬영 안내와 입력은 JPG/PNG 한 장만 받는다', async ({ page }) => {
  await authenticate(page);
  await page.goto('/document-upload');

  await expect(page.getByRole('heading', { name: '복약안내문을 한 장 담아주세요' })).toBeVisible();
  await expect(
    page.getByRole('img', {
      name: '네 테두리가 모두 보이도록 평평하게 놓고 바로 위에서 촬영한 복약안내문 예시',
    }),
  ).toBeVisible();
  await expect(page.getByText('이 네 가지가 보이게 담아주세요', { exact: true })).toBeVisible();
  await expect(page.getByRole('list').getByRole('listitem')).toHaveText([
    '병원명',
    '조제일',
    '약품명·함량',
    '1회 투약량·횟수·일수',
  ]);

  const camera = page.getByLabel('카메라로 약봉투 촬영');
  const gallery = page.getByLabel('갤러리에서 약봉투 선택');
  await expect(camera).toHaveAttribute('accept', 'image/jpeg,image/png');
  await expect(camera).toHaveAttribute('capture', 'environment');
  await expect(camera).not.toHaveAttribute('multiple');
  await expect(gallery).toHaveAttribute('accept', 'image/jpeg,image/png');
  await expect(gallery).not.toHaveAttribute('capture');
  await expect(gallery).not.toHaveAttribute('multiple');
});

for (const width of [320, 390]) {
  test(`선택한 약봉투 원본을 100~300%로 확대하고 이동한 뒤 다시 열면 초기화한다 (${width}px)`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticate(page);
    await page.goto('/document-upload');
    await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({
      name: 'medication-capture-guide.png',
      mimeType: 'image/png',
      buffer: MEDICATION_CAPTURE_GUIDE_PNG,
    });

    const trigger = page.getByRole('button', { name: '선택한 약봉투 크게 보기' });
    const selectedPreview = page.getByRole('img', { name: '선택한 약봉투 미리보기' });
    const selectedSrc = await selectedPreview.getAttribute('src');
    expect(selectedSrc).toMatch(/^blob:/);
    await trigger.click();

    const viewer = page.getByRole('dialog', { name: '선택한 약봉투 크게 보기' });
    const image = viewer.getByRole('img', { name: '확대한 약봉투 원본' });
    const scrollArea = viewer.getByRole('region', { name: '확대한 약봉투 이동 영역' });
    const zoomIn = viewer.getByRole('button', { name: '확대', exact: true });
    const zoomOut = viewer.getByRole('button', { name: '축소', exact: true });
    const zoomStatus = viewer.getByRole('status', { name: '확대 비율' });
    const close = viewer.getByRole('button', { name: '닫기', exact: true });
    await expect(image).toBeVisible();
    await expect(image).toHaveAttribute('src', selectedSrc ?? '');
    await expect(zoomStatus).toHaveText('100%');
    await expect(zoomOut).toBeDisabled();
    const baselineBox = await image.boundingBox();
    expect(baselineBox).not.toBeNull();

    await zoomIn.click();
    await expect(zoomStatus).toHaveText('150%');
    await zoomIn.click();
    await expect(zoomStatus).toHaveText('200%');
    await zoomIn.click();
    await expect(zoomStatus).toHaveText('300%');
    await expect(zoomIn).toBeDisabled();
    const zoomedBox = await image.boundingBox();
    expect(zoomedBox).not.toBeNull();
    expect(zoomedBox!.width / baselineBox!.width).toBeGreaterThanOrEqual(2.99);
    expect(zoomedBox!.width / baselineBox!.width).toBeLessThanOrEqual(3.01);

    await scrollArea.evaluate((element) => element.scrollTo({
      left: element.scrollWidth,
      top: element.scrollHeight,
    }));
    await expect.poll(() => scrollArea.evaluate((element) => ({
      atRight: Math.abs(element.scrollLeft - (element.scrollWidth - element.clientWidth)) <= 1,
      atBottom: Math.abs(element.scrollTop - (element.scrollHeight - element.clientHeight)) <= 1,
    }))).toEqual({ atRight: true, atBottom: true });

    for (const control of [zoomOut, zoomIn, close]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await viewer.evaluate((element) => element.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`document-upload-preview-zoom-${width}.png`) });
    await image.click();
    await expect(viewer).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await expect(zoomStatus).toHaveText('100%');
    await expect(zoomOut).toBeDisabled();
    await expect.poll(() => scrollArea.evaluate((element) => ({
      left: element.scrollLeft,
      top: element.scrollTop,
    }))).toEqual({ left: 0, top: 0 });
    await close.click();
    await expect(viewer).toHaveCount(0);
    await trigger.click();
    await page.keyboard.press('Escape');
    await expect(viewer).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
}

test('조제일은 서울 오늘로부터 31일 뒤까지 수정하고 저장할 수 있다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await authenticate(page);
  await interceptDefaultNotifySettings(page);
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
  await page.route('**/api/v1/ocr/jobs/b_mock_9f21/*image', async (route) => {
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

  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21&flow=registration',
  );
  expect(patches).toHaveLength(1);
  expect((JSON.parse(patches[0].body) as { dispensedDate: string }).dispensedDate).toBe(
    '2026-09-25',
  );
});

for (const failFirst of [false, true]) {
  test(`동일 File 업로드는 진행 중 요청을 공유하고 ${failFirst ? '실패' : '성공'} 후 재시도한다`, async ({ page }) => {
    await authenticate(page);
    const uploads: CapturedRequest[] = [];
    let releaseUploads!: () => void;
    const pending = new Promise<void>(resolve => { releaseUploads = resolve; });
    await page.route('**/api/v1/ocr', async route => {
      uploads.push(capture(route));
      const attempt = uploads.length;
      await pending;
      await fulfillJson(route, failFirst && attempt === 1
        ? { message: 'temporary upload failure' }
        : { documentIds: [attempt], ocrStatus: 'queued' },
      failFirst && attempt === 1 ? 503 : 200);
    });
    await page.goto('/document-upload');
    const outcome = page.evaluate(async () => {
      const modulePath = '/src/entities/document/api.ts';
      const { uploadDocument } = await import(modulePath);
      const file = new File(['photo'], 'photo.png', { type: 'image/png' });
      const first = uploadDocument(file);
      const duplicate = uploadDocument(file);
      // 같은 이름과 내용이라도 다른 File 객체이면 독립 요청입니다.
      const other = uploadDocument(new File(['photo'], 'photo.png', { type: 'image/png' }));
      const results = await Promise.allSettled([first, duplicate, other]);
      const retry = uploadDocument(file);
      const retryDuplicate = uploadDocument(file);
      const retried = await Promise.all([retry, retryDuplicate]);
      return {
        sharedPromise: first === duplicate,
        statuses: results.map(result => result.status),
        sharedOutcome: results[0].status === 'fulfilled' && results[1].status === 'fulfilled'
          ? results[0].value === results[1].value
          : results[0].status === 'rejected' && results[1].status === 'rejected'
            && results[0].reason === results[1].reason,
        retrySharedPromise: retry === retryDuplicate,
        retried,
      };
    });
    // 다른 파일도 첫 파일의 응답을 기다리지 않고 전송되어야 합니다.
    await expect.poll(() => uploads.length).toBeGreaterThanOrEqual(2);
    releaseUploads();
    const result = await outcome;
    expect(uploads).toHaveLength(3);
    expect(result.sharedPromise).toBe(true);
    expect(result.sharedOutcome).toBe(true);
    expect(result.statuses).toEqual([failFirst ? 'rejected' : 'fulfilled', failFirst ? 'rejected' : 'fulfilled', 'fulfilled']);
    expect(result.retrySharedPromise).toBe(true);
    expect(result.retried).toEqual([
      { documentIds: [3], ocrStatus: 'queued' },
      { documentIds: [3], ocrStatus: 'queued' },
    ]);
    const keys = uploads.map(upload => upload.headers['idempotency-key']);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).not.toBe(keys[0]);
    expect(keys[2]).toBe(keys[0]);
  });
}

test('HTTP 모바일에서 randomUUID 없이 촬영 사진을 업로드하고 OCR 결과를 표시한다', async ({ page }, testInfo) => {
  test.slow();
  await authenticate(page);
  await page.addInitScript(() => {
    Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: undefined });
  });
  const trace = await interceptDocumentRegistration(page);
  await page.goto('/document-upload');
  await page.getByLabel('카메라로 약봉투 촬영').setInputFiles({
    name: 'camera-photo.png',
    mimeType: 'image/png',
    buffer: ONE_PIXEL_PNG,
  });
  await page.getByRole('button', { name: '등록하기' }).click();
  await expect.poll(() => trace.uploads.length).toBeGreaterThan(0);
  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible({ timeout: 10_000 });
  expect(trace.uploads).toHaveLength(1);
  expect(trace.uploads[0].body).toContain('filename="camera-photo.png"');
  expect(trace.uploads[0].headers['idempotency-key']).toBeTruthy();
  expect(trace.polls).toHaveLength(3);
  await page.screenshot({ path: testInfo.outputPath('mobile-ocr-result.png'), fullPage: true });

  // 재시도는 같은 키를 유지하고 별도 촬영 파일은 새 키를 받아야 합니다.
  await page.evaluate(async () => {
    const modulePath = '/src/entities/document/api.ts';
    const { uploadDocument } = await import(modulePath);
    const file = new File(['retry'], 'retry.png', { type: 'image/png' });
    await uploadDocument(file);
    await uploadDocument(file);
    await uploadDocument(new File(['retry'], 'retry.png', { type: 'image/png' }));
  });
  const keys = trace.uploads.slice(-3).map((request) => request.headers['idempotency-key']);
  expect(keys[0]).toBeTruthy();
  expect(keys[0]).toBe(keys[1]);
  expect(keys[2]).not.toBe(keys[0]);
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
  await expect(page.getByRole('article', { name: /파모티딘 원문/ })).not.toContainText('확인 필요');
  await expect(page.getByRole('img', { name: '약봉투 미리보기' })).toHaveAttribute(
    'src',
    /^blob:/,
  );

  const unextractedMedication = page.getByRole('article', { name: /파모티딘 원문/ });
  await unextractedMedication.getByRole('button', { name: /수정$/ }).click();
  await expect(page.getByRole('dialog').getByLabel('함량', { exact: true })).toHaveValue('');
  await expect(page.getByRole('dialog').getByLabel('1회 투약량', { exact: true })).toHaveValue('');
  await page.getByRole('dialog').getByRole('button', { name: '닫기', exact: true }).click();

  await page.getByRole('button', { name: '리바록사반 수정', exact: true }).click();
  const editDialog = page.getByRole('dialog');
  await editDialog.getByLabel('약품명').fill('리바록사반 수정');
  await editDialog.getByLabel('함량').fill('15mg');
  await editDialog.getByLabel('1회 투약량').fill('0.5정');
  await editDialog.getByRole('button', { name: '저장', exact: true }).click();
  const editedMedication = page.getByRole('article', { name: '리바록사반 수정', exact: true });
  await editedMedication.getByRole('button', { name: '리바록사반 수정 수정', exact: true }).click();
  await expect(page.getByRole('dialog').getByLabel('함량', { exact: true })).toHaveValue('15mg');
  await page.getByRole('dialog').getByRole('button', { name: '닫기', exact: true }).click();

  await page.getByRole('button', { name: '아세트아미노펜 수정', exact: true }).click();
  const prnDialog = page.getByRole('dialog');
  await prnDialog.getByRole('combobox').click();
  await page.getByRole('option', { name: '필요 시', exact: true }).click();
  await prnDialog.getByRole('button', { name: '저장', exact: true }).click();

  await page.getByRole('button', { name: /파모티딘 원문 수정$/ }).click();
  const sourceNameDialog = page.getByRole('dialog');
  await sourceNameDialog.getByLabel('1회 투약량').fill('0.75');
  await sourceNameDialog.getByRole('button', { name: '저장', exact: true }).click();

  await page.getByRole('button', { name: '직접 추가', exact: true }).click();
  const addDialog = page.getByRole('dialog');
  await addDialog.getByLabel('약품명').fill('새 약');
  await addDialog.getByLabel('함량').fill('500mg');
  await addDialog.getByLabel('1회 투약량').fill('1캡슐');
  await addDialog.getByLabel('복용 일수').fill('7');
  await addDialog.getByRole('combobox').click();
  await page.getByRole('option', { name: '2회', exact: true }).click();
  await addDialog.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('heading', { name: '약 5개' })).toBeVisible();

  await page.getByRole('button', { name: '셀레콕시브 수정', exact: true }).click();
  const deleteDialog = page.getByRole('dialog');
  await deleteDialog.getByRole('button', { name: '이 약 삭제' }).click();
  await deleteDialog.getByRole('button', { name: '삭제', exact: true }).click();
  await expect(page.getByRole('article', { name: '셀레콕시브', exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await expect(page.getByRole('button', { name: '확인 후 저장' })).toHaveCount(0);
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=314&ocrJobId=501&flow=registration',
  );
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
    hospitalName: string;
    dispensedDate: string;
    alias: string | null;
    medications: Array<Record<string, unknown>>;
  };
  expect(Object.keys(patchPayload).sort()).toEqual([
    'alias',
    'dispensedDate',
    'hospitalName',
    'medications',
  ]);
  expect(patchPayload.hospitalName).toBe('송도센트럴이비인후과의원');
  expect(patchPayload.dispensedDate).toBe('2026-08-22');
  expect(patchPayload.alias).toBe('송도센트럴이비인후과의원');
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
      { tempId: 'm4', name: ' 파모티딘 원문 ', doseQuantity: '0.75', timesPerDay: 1, days: 7 },
      {
        tempId: expect.stringMatching(/^new_/),
        name: '새 약',
        strength: '500mg',
        doseQuantity: '1캡슐',
        timesPerDay: 2,
        days: 7,
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
  await stubNonMedicationHomeData(page);
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
  await stubNonMedicationHomeData(page);
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
  await stubNonMedicationHomeData(page);
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

test('복용 기록은 사용자 단위로 한 번만 조회하고, 선택한 처방마다 저장한다', async ({
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
    .getByRole('button', { name: '먹었어요' });
  await action.click();

  await expect(page.getByRole('button', { name: '복약 기록 되돌리기' })).toBeVisible();
  expect(doseGets).toHaveLength(1);
  expect(new URL(doseGets[0]).searchParams.has('recordId')).toBe(false);
  expect(dosePosts).toHaveLength(2);
  expect([...dosePosts].sort((left, right) => Number(left.recordId) - Number(right.recordId))).toEqual([
    { date: '2026-08-25', slot: 'morning', taken: true, recordId: 12 },
    { date: '2026-08-25', slot: 'morning', taken: true, recordId: 24 },
  ]);
});

test('처방 2개 중 1개만 기록하고 새로고침해도 그 처방만 완료다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const storedDoses: Array<Record<string, unknown>> = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, storedDoses, 200);
      return;
    }
    const payload = request.postDataJSON() as Record<string, unknown>;
    storedDoses.splice(
      0,
      storedDoses.length,
      ...storedDoses.filter(
        (dose) =>
          dose.date !== payload.date || dose.slot !== payload.slot || dose.recordId !== payload.recordId,
      ),
    );
    if (payload.taken) storedDoses.push(payload);
    await fulfillJson(route, payload, 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/dev/home-multiple-episodes');
  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  const secondEpisode = morning.getByRole('article', { name: /8월 24일 처방/ });
  await firstEpisode.getByRole('button', { name: /8월 22일 처방.*선택/ }).click();
  await morning.getByRole('button', { name: '먹었어요' }).click();
  await expect(page.getByRole('button', { name: '되돌리기', exact: true })).toBeVisible();
  await page.reload();

  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
  expect(storedDoses).toEqual([
    { date: '2026-08-25', slot: 'morning', taken: true, recordId: 12 },
  ]);
});

test('복약 저장 중에는 선택 행과 복약 액션을 잠가 반대 작업이 겹치지 않게 한다', async ({
  page,
}) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const dosePosts: Array<Record<string, unknown>> = [];
  let releaseSave!: () => void;
  const saveGate = new Promise<void>((resolve) => {
    releaseSave = resolve;
  });
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, [], 200);
      return;
    }
    dosePosts.push(request.postDataJSON() as Record<string, unknown>);
    await saveGate;
    await fulfillJson(route, request.postDataJSON(), 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/dev/home-multiple-episodes');
  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  const firstSelector = firstEpisode.locator('[data-episode-row]');
  await firstSelector.click();
  await morning.getByRole('button', { name: '먹었어요' }).click();

  try {
    await expect(firstSelector).toBeDisabled({ timeout: 1_000 });
    await expect(morning.getByRole('button', { name: /먹었어요|복약 기록 되돌리기/ })).toBeDisabled();
    expect(dosePosts).toHaveLength(1);
  } finally {
    releaseSave();
  }

  await expect(firstEpisode.getByRole('button', { name: /8월 22일 처방.*복용 완료/ })).toBeEnabled();
  expect(dosePosts).toHaveLength(1);
});

test('여러 처방 저장 중 실패한 처방만 롤백한다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const savedRecordIds: number[] = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, [], 200);
      return;
    }
    const payload = request.postDataJSON() as { recordId: number };
    if (payload.recordId === 24) {
      await fulfillJson(route, { code: 'INTERNAL_ERROR', message: '실패' }, 500);
      return;
    }
    savedRecordIds.push(payload.recordId);
    await fulfillJson(route, payload, 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/dev/home-multiple-episodes');
  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = page.locator('[role="group"][aria-label="아침약 상세"] article[aria-label*="8월 22일 처방"]');
  const secondEpisode = page.locator('[role="group"][aria-label="아침약 상세"] article[aria-label*="8월 24일 처방"]');
  await morning.getByRole('button', { name: '먹었어요' }).click();

  await expect(page.getByRole('dialog', { name: '기록하지 못했어요' })).toBeVisible();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await expect(firstEpisode.locator('[data-episode-row]')).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await expect(firstEpisode.locator('[data-episode-selection-glyph] svg')).toHaveCount(0);
  await expect(secondEpisode.locator('[data-episode-row]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(secondEpisode.locator('[data-episode-selection-glyph] svg')).toHaveCount(1);
  expect(savedRecordIds).toEqual([12]);
});

test('부분 실패는 실패 회차만 선택하고 팝업 재시도 성공 후 선택을 해제한다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const dosePosts: number[] = [];
  let failSecondOnce = true;
  let releaseRetry!: () => void;
  const retryGate = new Promise<void>((resolve) => {
    releaseRetry = resolve;
  });
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, [], 200);
      return;
    }
    const payload = request.postDataJSON() as { recordId: number };
    dosePosts.push(payload.recordId);
    if (payload.recordId === 24 && failSecondOnce) {
      failSecondOnce = false;
      await fulfillJson(route, { code: 'INTERNAL_ERROR', message: '실패' }, 500);
      return;
    }
    if (payload.recordId === 24) await retryGate;
    await fulfillJson(route, payload, 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/dev/home-multiple-episodes');
  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = page.locator('[role="group"][aria-label="아침약 상세"] article[aria-label*="8월 22일 처방"]');
  const secondEpisode = page.locator('[role="group"][aria-label="아침약 상세"] article[aria-label*="8월 24일 처방"]');
  const firstSelector = firstEpisode.locator('[data-episode-row]');
  const secondSelector = secondEpisode.locator('[data-episode-row]');
  await firstSelector.click();
  await secondSelector.click();
  await morning.getByRole('button', { name: '먹었어요' }).click();

  const dialog = page.getByRole('dialog', { name: '기록하지 못했어요' });
  await expect(dialog).toBeVisible();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  await expect(firstSelector).toHaveAttribute('aria-pressed', 'false');
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await expect(secondSelector).toHaveAttribute('aria-pressed', 'true');

  await dialog.getByRole('button', { name: '다시 시도' }).click();
  await expect(dialog).toHaveCount(0);
  await expect.poll(() => dosePosts.length).toBe(3);
  try {
    await expect(secondSelector).toBeDisabled({ timeout: 1_000 });
    await expect(morning.getByRole('button', { name: '복약 기록 되돌리기' })).toBeDisabled();
  } finally {
    releaseRetry();
  }
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  await expect(secondSelector).toHaveAttribute('aria-pressed', 'false');
  await expect(morning.getByRole('button', { name: '복약 기록 되돌리기' })).toBeDisabled();
  expect([...dosePosts].sort((left, right) => left - right)).toEqual([12, 24, 24]);
});

test('토스트 되돌리기 실패는 완료를 유지하고 팝업 재시도에서 false를 다시 전송한다', async ({
  page,
}) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const dosePosts: Array<{ recordId: number; taken: boolean }> = [];
  let failUndoOnce = true;
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, [], 200);
      return;
    }
    const payload = request.postDataJSON() as { recordId: number; taken: boolean };
    dosePosts.push({ recordId: payload.recordId, taken: payload.taken });
    if (!payload.taken && failUndoOnce) {
      failUndoOnce = false;
      await fulfillJson(route, { code: 'INTERNAL_ERROR', message: '실패' }, 500);
      return;
    }
    await fulfillJson(route, payload, 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/dev/home-multiple-episodes');
  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = page.locator('[role="group"][aria-label="아침약 상세"] article[aria-label*="8월 22일 처방"]');
  await firstEpisode.locator('[data-episode-row]').click();
  await morning.getByRole('button', { name: '먹었어요' }).click();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();

  await page.getByRole('button', { name: '되돌리기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '기록하지 못했어요' });
  await expect(dialog).toBeVisible();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();

  await dialog.getByRole('button', { name: '다시 시도' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
  expect(dosePosts).toEqual([
    { recordId: 12, taken: true },
    { recordId: 12, taken: false },
    { recordId: 12, taken: false },
  ]);
});

test('A와 B를 기록한 뒤 A 토스트를 되돌려도 B 완료 상태를 유지한다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const dosePosts: Array<{ recordId: number; taken: boolean }> = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, [], 200);
      return;
    }
    const payload = request.postDataJSON() as { recordId: number; taken: boolean };
    dosePosts.push({ recordId: payload.recordId, taken: payload.taken });
    await fulfillJson(route, payload, 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/dev/home-multiple-episodes');
  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = page.locator('[role="group"][aria-label="아침약 상세"] article[aria-label*="8월 22일 처방"]');
  const secondEpisode = page.locator('[role="group"][aria-label="아침약 상세"] article[aria-label*="8월 24일 처방"]');
  await firstEpisode.locator('[data-episode-row]').click();
  await morning.getByRole('button', { name: '먹었어요' }).click();
  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  await secondEpisode.locator('[data-episode-row]').click();
  await morning.getByRole('button', { name: '먹었어요' }).click();
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toBeVisible();

  const olderToast = page.locator('[data-sonner-toast][data-index="1"]');
  await page.locator('[data-sonner-toast][data-index="0"]').hover();
  await expect(olderToast).toBeVisible();
  await olderToast.getByRole('button', { name: '되돌리기' }).click();

  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  expect(dosePosts).toEqual([
    { recordId: 12, taken: true },
    { recordId: 24, taken: true },
    { recordId: 12, taken: false },
  ]);
});

test('이미 완료된 처방과 함께 기록한 batch를 되돌려도 기존 완료는 유지한다', async ({ page }) => {
  await authenticate(page);
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  const storedDoses: Array<Record<string, unknown>> = [
    { date: '2026-08-25', slot: 'morning', taken: true, recordId: 12 },
  ];
  const dosePosts: Array<Record<string, unknown>> = [];
  await page.route('**/api/v1/medications/doses*', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, storedDoses, 200);
      return;
    }
    const payload = request.postDataJSON() as Record<string, unknown>;
    dosePosts.push(payload);
    const remaining = storedDoses.filter(
      (dose) =>
        dose.date !== payload.date || dose.slot !== payload.slot || dose.recordId !== payload.recordId,
    );
    storedDoses.splice(0, storedDoses.length, ...remaining);
    if (payload.taken) storedDoses.push(payload);
    await fulfillJson(route, payload, 200);
  });
  await page.route('**/api/v1/display/med/nutr/rank*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );
  await page.route('**/api/v1/med/user-suppl-nutr*', (route) =>
    fulfillJson(route, { code: 'NOT_FOUND', message: 'Not found' }, 404),
  );

  await page.goto('/dev/home-multiple-episodes');
  const morning = page
    .getByRole('region', { name: '오늘의 복약' })
    .getByRole('group', { name: '아침약 상세' });
  const firstEpisode = morning.getByRole('article', { name: /8월 22일 처방/ });
  const secondEpisode = morning.getByRole('article', { name: /8월 24일 처방/ });
  await morning.getByRole('button', { name: '먹었어요' }).click();
  await expect(page.getByRole('button', { name: '되돌리기', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '되돌리기', exact: true }).click();

  await expect(firstEpisode.locator('[data-episode-completed-badge]')).toBeVisible();
  await expect(secondEpisode.locator('[data-episode-completed-badge]')).toHaveCount(0);
  expect(dosePosts).toEqual([
    { date: '2026-08-25', slot: 'morning', taken: true, recordId: 24 },
    { date: '2026-08-25', slot: 'morning', taken: false, recordId: 24 },
  ]);
  expect(storedDoses).toEqual([
    { date: '2026-08-25', slot: 'morning', taken: true, recordId: 12 },
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
  await page.getByRole('button', { name: '선택', exact: true }).click();
  await page.getByRole('checkbox', { name: /2026년 8월 22일 처방 선택/ }).check();
  await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
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

test('RAM 전처리 이미지가 404여도 medium OCR 결과를 확인하고 저장한다', async ({ page }) => {
  await authenticate(page);
  const images: CapturedRequest[] = [];
  const patches: CapturedRequest[] = [];
  const mediumOnlyResult = {
    ...readyOcrResult,
    batchId: String(DOCUMENT_ID),
    medications: [{ ...readyOcrResult.medications[0], confidence: 'medium' }],
    lowConfidenceCount: 0,
  };

  await page.route('**/api/v1/ocr', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, { batchId: 'upload-batch-501', documentIds: [DOCUMENT_ID], ocrStatus: 'queued' });
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === OCR_URL) {
      await fulfillJson(route, mediumOnlyResult);
      return;
    }
    if (request.method() === 'GET' && path === `${OCR_URL}/processed-image`) {
      images.push(capture(route));
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'image_unavailable', message: '원본 이미지를 불러올 수 없어요.' }),
      });
      return;
    }
    if (request.method() === 'PATCH' && path === OCR_URL) {
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

  await page.goto('/document-upload');
  await selectGalleryPng(page);
  await page.getByRole('button', { name: '등록하기', exact: true }).click();
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByText('내용을 잘 읽었어요')).toBeVisible();
  await expect(page.getByText('1곳만 확인해주세요')).toHaveCount(0);
  await expect(page.getByText('확인 권장', { exact: true })).toHaveCount(0);
  await expect(page.getByText('사진 미리보기를 사용할 수 없어요')).toBeVisible();
  await expect(page.getByRole('img', { name: '등록한 약봉투 원본' })).toHaveCount(0);

  const saveButton = page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true });
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=501&flow=registration',
  );

  expect(patches).toHaveLength(1);
  expect(images).toHaveLength(1);
  expect(new URL(images[0].url).pathname).toBe(`${OCR_URL}/processed-image`);
  expectAuthenticated(images);
  expectAuthenticated(patches);
});

test('OCR 별칭 저장이 실패해도 같은 확정을 재시도하고 중복 회차를 만들지 않는다', async ({ page }) => {
  await authenticate(page);
  const patches: CapturedRequest[] = [];
  const mediumOnlyResult = {
    ...readyOcrResult,
    batchId: 'b_mock_9f21',
  };

  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      await fulfillJson(route, mediumOnlyResult);
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
    if (request.method() === 'PATCH' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      patches.push(capture(route));
      if (patches.length === 1) {
        await fulfillJson(route, { code: 'temporary', message: '잠시 후 다시 시도해주세요.' }, 503);
      } else {
        await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      }
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/med/medication/schedule/**', async (route) => {
    await fulfillJson(route, { start: null, mealTimes: null, medications: [] });
  });

  await page.goto('/dev/ocr-review');
  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await page.getByLabel('복약 별칭').fill('재시도 OCR 처방');
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await page.getByRole('dialog', { name: '확인이 필요한 항목을 모두 보셨나요?' })
    .getByRole('button', { name: '확인 후 저장', exact: true })
    .click();

  const errorDialog = page.getByRole('dialog').filter({ hasText: '저장하지 못했어요' });
  await expect(errorDialog).toBeVisible();
  await expect(page.getByLabel('복약 별칭')).toHaveValue('재시도 OCR 처방');
  await errorDialog.getByRole('button', { name: '다시 시도', exact: true }).click();
  await expect(page).toHaveURL(
    '/medication-schedule?recordId=315&ocrJobId=b_mock_9f21&flow=registration',
  );

  expect(patches).toHaveLength(2);
  expect(patches.map((request) => (JSON.parse(request.body) as { alias: string | null }).alias)).toEqual([
    '재시도 OCR 처방',
    '재시도 OCR 처방',
  ]);
});

for (const headerOnly of [false, true]) {
  test(`약이 추출되지 않으면 문서 재등록을 안내한다 (병원명만 추출: ${headerOnly})`, async ({ page }) => {
    await authenticate(page);
    await page.route('**/api/v1/ocr/jobs/501', route => fulfillJson(route, {
      ...readyOcrResult,
      fields: headerOnly ? readyOcrResult.fields : {},
      medications: [],
      lowConfidenceCount: 0,
    }));
    await page.route('**/api/v1/ocr/jobs/501/**', route => route.fulfill({ status: 404 }));
    let cancelCount = 0;
    await page.route('**/api/v1/ocr/jobs/501/cancel', async (route) => {
      expect(route.request().method()).toBe('POST');
      cancelCount += 1;
      await route.fulfill({ status: 204 });
    });
    await page.goto('/ocr-review?batchId=501');
    await expect(page.getByText('약 정보를 추출하지 못했어요', { exact: true })).toBeVisible();
    await expect(page.getByText('문서를 다시 등록해주세요', { exact: true })).toBeVisible();
    const failureDialog = page.getByRole('dialog', { name: '문서를 읽지 못했어요' });
    await expect(failureDialog).toBeVisible();
    await expect(page.getByLabel('복약 별칭')).toHaveCount(0);
    await expect(page.getByText('저장 완료', { exact: true })).toHaveCount(0);
    await expect(page.getByText('내용을 잘 읽었어요', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true })).toHaveCount(0);
    await page.screenshot({ path: `test-results/empty-ocr-${headerOnly}.png`, fullPage: true });
    if (headerOnly) {
      await failureDialog.getByRole('button', { name: '그대로 직접 입력', exact: true }).click();
      await expect(page.getByText('약 정보를 직접 입력해주세요', { exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: '직접 추가' })).toBeVisible();
    } else {
      await failureDialog.getByRole('button', { name: '문서 다시 등록', exact: true }).click();
      await expect(page).toHaveURL(/\/document-upload$/);
      expect(cancelCount).toBe(1);
    }
  });
}

test('명시적 재촬영 OCR 실패만 사진 품질 안내를 표시한다', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/v1/ocr/jobs/recapture-required', route => fulfillJson(route, {
    batchId: 'recapture-required',
    ocrStatus: 'failed',
    errorCode: 'RECAPTURE_REQUIRED',
  }));

  await page.goto('/ocr-review?batchId=recapture-required');

  await expect(page.getByText('문서를 다시 등록해주세요', { exact: true })).toBeVisible();
  await expect(
    page.getByText('문서의 네 모서리와 글자가 선명하게 보이는 사진으로 다시 등록해주세요.'),
  ).toBeVisible();
  const failureDialog = page.getByRole('dialog', { name: '문서를 읽지 못했어요' });
  await expect(failureDialog).toBeVisible();
  await expect(failureDialog.getByRole('button', { name: '문서 다시 등록', exact: true })).toBeVisible();
  await expect(failureDialog.getByRole('button', { name: '그대로 직접 입력', exact: true })).toBeVisible();
});

test('이미 완료되었거나 실패한 문서 OCR 상태를 기존 화면으로 보여준다', async ({ page }) => {
  await authenticate(page);
  await interceptDefaultNotifySettings(page);
  let failed = false;
  const patches: CapturedRequest[] = [];
  await page.route('**/api/v1/med/medication/schedule/**', route => fulfillJson(route, {
    start: null, mealTimes: null, medications: [],
  }));
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'PATCH' && path === '/api/v1/ocr/jobs/b_mock_9f21') {
      patches.push(capture(route));
      await fulfillJson(route, { recordId: 315, hasMedication: true, statusCode: 'active' });
      return;
    }
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
  await expect(failureDialog.getByRole('heading', { name: '약 정보를 확인하지 못했어요' })).toBeVisible();
  await expect(failureDialog.getByRole('button', { name: '문서 다시 등록' })).toBeVisible();
  await expect(failureDialog.getByRole('button', { name: '그대로 직접 입력' })).toBeVisible();
  await expect(page.getByText('추출 중 문제가 생겼어요', { exact: true })).toBeVisible();
  await expect(
    failureDialog.getByText('약 정보를 추출하는 중 문제가 생겼어요. 잠시 후 문서를 다시 등록하거나 직접 입력할 수 있어요.'),
  ).toBeVisible();
  await expect(page.getByText('문서를 다시 등록해주세요', { exact: true })).toHaveCount(0);
  await expect(
    page.getByText('문서의 네 모서리와 글자가 선명하게 보이는 사진으로 다시 등록해주세요.'),
  ).toHaveCount(0);
  await expect(page.getByLabel('복약 별칭')).toHaveCount(0);
  await expect(page.getByText('나머지는 잘 읽혔습니다.', { exact: false })).toHaveCount(0);
  await page.screenshot({ path: 'test-results/failed-ocr-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: 'test-results/failed-ocr-desktop.png', fullPage: true });
  await failureDialog.getByRole('button', { name: '그대로 직접 입력' }).click();
  await expect(failureDialog).toHaveCount(0);
  await expect(page.getByText('약 정보를 직접 입력해주세요', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '직접 추가' })).toBeVisible();
  await page.getByLabel('조제일', { exact: true }).fill('2026-08-22');
  await page.getByRole('button', { name: '직접 추가', exact: true }).click();
  const medicationDialog = page.getByRole('dialog', { name: '약 추가' });
  await medicationDialog.getByLabel('약품명').fill('직접입력약');
  await medicationDialog.getByLabel('복용 일수').fill('7');
  await medicationDialog.getByRole('combobox').click();
  await page.getByRole('option', { name: '1회', exact: true }).click();
  await medicationDialog.getByRole('button', { name: '저장', exact: true }).click();
  await page.getByRole('button', { name: '저장하고 복약 시간 설정', exact: true }).click();
  await expect(page).toHaveURL('/medication-schedule?recordId=315&ocrJobId=b_mock_9f21&flow=registration');
  expect(patches).toHaveLength(1);
  expect(JSON.parse(patches[0].body).medications[0].name).toBe('직접입력약');
  await page.goBack();
  await expect(page.getByRole('article', { name: /직접입력약/ })).toBeVisible();
  await expect(page.getByRole('dialog', { name: '문서를 읽지 못했어요' })).toHaveCount(0);
});
