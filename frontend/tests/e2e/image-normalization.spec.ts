import { expect, test } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8+QAAAABJRU5ErkJggg==',
  'base64',
);

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

async function authenticate(page: import('playwright/test').Page) {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('poke.access-token', 'image-normalization-e2e-token');
    window.sessionStorage.setItem('poke.account-principal', 'image-normalization@example.com');
  });
}

test('단일 HEIC 사진은 선택할 수 있고 브라우저 미리보기가 안 되어도 등록할 수 있다', async ({ page }, testInfo) => {
  await authenticate(page);
  await page.goto('/document-upload');

  const gallery = page.getByLabel('갤러리에서 약봉투 선택');
  await expect(gallery).toHaveAttribute(
    'accept',
    /image\/jpeg.*image\/png.*image\/heic.*image\/heif.*image\/webp.*image\/bmp.*image\/tiff/,
  );

  await gallery.setInputFiles({
    name: 'iphone-photo.HEIC',
    mimeType: 'image/heic',
    buffer: Buffer.from('not-browser-decodable-heic'),
  });

  await expect(page.getByText('이 사진으로 등록할까요?')).toBeVisible();
  await expect(page.getByText('이 브라우저에서는 미리보기를 지원하지 않아요. 사진은 그대로 등록할 수 있어요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '등록하기' })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('heic-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath('heic-desktop.png'), fullPage: true });
  const message = '단일 사진만 지원합니다. GIF나 여러 이미지가 포함된 파일은 사용할 수 없습니다.';
  let received = false;
  await page.route('**/api/v1/ocr', async (route) => {
    const body = route.request().postDataBuffer()?.toString() ?? '';
    received = body.includes('iphone-photo.HEIC') && body.includes('not-browser-decodable-heic');
    await route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ code: 'MULTI_IMAGE_NOT_SUPPORTED', message }) });
  });
  await page.getByRole('button', { name: '등록하기', exact: true }).click();
  await expect(page.getByText(message)).toBeVisible();
  expect(received).toBe(true);
});

test('GIF는 선택 직후 단일 사진이 아니라는 안내를 하고 등록하지 않는다', async ({ page }) => {
  await authenticate(page);
  await page.goto('/document-upload');

  await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({
    name: 'animated.gif',
    mimeType: 'image/gif',
    buffer: Buffer.from('GIF89a'),
  });

  await expect(page.getByRole('alert')).toHaveText('GIF는 지원하지 않아요. 한 장의 사진을 선택해주세요.');
  await expect(page.getByRole('heading', { name: '복약안내문을 한 장 담아주세요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '등록하기' })).toHaveCount(0);
});

test('HEIC 검토 원본은 서버 정상화 이미지로 표시한 뒤 임시 사진을 해제한다', async ({ page }) => {
  await authenticate(page);
  const requests: string[] = [];
  const jobUrl = '/api/v1/ocr/jobs/77';
  await page.route('**/api/v1/ocr', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ documentIds: [77], ocrStatus: 'queued' }),
      });
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/ocr/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push(`${request.method()} ${path}`);
    if (request.method() === 'GET' && path === jobUrl) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          batchId: '77',
          ocrStatus: 'ready_for_review',
          documentImageUrl: '/not-used-directly',
          fields: {},
          medications: [{ tempId: 'm1', name: '테스트약', confidence: 'high' }],
          lowConfidenceCount: 0,
        }),
      });
      return;
    }
    if (request.method() === 'GET' && (path === `${jobUrl}/image` || path === `${jobUrl}/processed-image`)) {
      await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG });
      return;
    }
    if (request.method() === 'POST' && path === `${jobUrl}/release-images`) {
      await route.fulfill({ status: 204 });
      return;
    }
    await route.continue();
  });

  await page.goto('/document-upload');
  await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({
    name: 'iphone-photo.heic',
    mimeType: 'image/heic',
    buffer: Buffer.from('not-browser-decodable-heic'),
  });
  await page.getByRole('button', { name: '등록하기', exact: true }).click();

  await expect(page.getByRole('heading', { name: '확인해주세요' })).toBeVisible();
  await expect(page.getByRole('img', { name: '약봉투 미리보기' })).toHaveAttribute('src', /^blob:/);
  await page.getByRole('button', { name: '약봉투 크게 보기' }).click();
  const viewer = page.getByRole('dialog', { name: '약봉투 이미지 크게 보기' });
  await viewer.getByRole('button', { name: '원본 보기', exact: true }).click();
  await expect(viewer.getByRole('img', { name: '확대한 약봉투 원본' })).toBeVisible();
  await expect.poll(() => requests).toEqual(expect.arrayContaining([
    `GET ${jobUrl}/image`,
    `GET ${jobUrl}/processed-image`,
    `POST ${jobUrl}/release-images`,
  ]));
});

test('미리보기 이미지 요청이 실패하면 탭 메모리 blob URL을 해제한다', async ({ page }) => {
  await authenticate(page);
  await page.addInitScript(() => {
    const original = URL.revokeObjectURL.bind(URL);
    let count = 0;
    URL.revokeObjectURL = (url) => {
      count += 1;
      original(url);
    };
    Object.defineProperty(window, '__revokedPreviewUrls', { get: () => count });
  });
  await page.route('**/api/v1/ocr', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ documentIds: [78] }) });
      return;
    }
    await route.continue();
  });
  await page.route('**/api/v1/ocr/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === 'GET' && path === '/api/v1/ocr/jobs/78') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          batchId: '78',
          ocrStatus: 'ready_for_review',
          documentImageUrl: '',
          fields: {},
          medications: [{ tempId: 'm1', name: '테스트약', confidence: 'high' }],
          lowConfidenceCount: 0,
        }),
      });
      return;
    }
    if (route.request().method() === 'GET' && path === '/api/v1/ocr/jobs/78/processed-image') {
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
      return;
    }
    await route.continue();
  });

  await page.goto('/document-upload');
  await page.getByLabel('갤러리에서 약봉투 선택').setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: ONE_PIXEL_PNG });
  await page.getByRole('button', { name: '등록하기', exact: true }).click();
  await expect(page.getByText('사진 미리보기를 사용할 수 없어요')).toBeVisible();
  expect(await page.evaluate(() => (window as Window & { __revokedPreviewUrls: number }).__revokedPreviewUrls)).toBeGreaterThan(0);
});
