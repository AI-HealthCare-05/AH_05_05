import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const ACCESS_TOKEN = 'e2e-camera-guide-token';

test.beforeEach(async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'camera-guide-e2e@example.com');
  }, ACCESS_TOKEN);
});

type CameraResponse = 'ready' | 'denied' | 'pending';

async function installCamera(page: Page, response: CameraResponse, options: { zoom?: boolean; still?: 'ready' | 'failed' | 'default-only' | 'oversized'; auto?: 'ready' | 'failed' } = {}) {
  await page.addInitScript(({ nextResponse, options }) => {
    const state = {
      requests: 0,
      stoppedTracks: 0,
      resolve: undefined as undefined | ((value: MediaStream) => void),
      stream: undefined as MediaStream | undefined,
      zoomValues: [] as number[],
      photoCalls: 0,
      autoModes: [] as string[],
      photoBlob: undefined as Blob | undefined,
    };

    const createTrackedStream = () => {
      const canvas = document.createElement('canvas');
      canvas.width = 720;
      canvas.height = 960;
      const context = canvas.getContext('2d');
      if (context) {
        context.fillStyle = '#cbd5e1';
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.fillStyle = '#ffffff';
        context.fillRect(120, 96, 480, 768);
        context.fillStyle = '#94a3b8';
        for (let line = 0; line < 8; line += 1) {
          context.fillRect(180, 190 + line * 70, 360, 18);
        }
      }
      const stream = canvas.captureStream();
      for (const track of stream.getTracks()) {
        let zoom = 1;
        if (options.zoom || options.auto) {
          const getSettings = track.getSettings.bind(track);
          Object.defineProperty(track, 'getCapabilities', { value: () => ({
            ...(options.zoom ? { zoom: { min: 1, max: 4, step: 0.5 } } : {}),
            ...(options.auto ? { focusMode: ['manual', 'continuous'], exposureMode: ['continuous'], whiteBalanceMode: ['manual'] } : {}),
          }) });
          Object.defineProperty(track, 'getSettings', { value: () => ({ ...getSettings(), zoom }) });
          Object.defineProperty(track, 'applyConstraints', { value: async (constraints: { advanced: Record<string, string | number>[] }) => {
            for (const settings of constraints.advanced) {
              for (const [name, value] of Object.entries(settings)) {
                if (name === 'zoom') { zoom = Number(value); state.zoomValues.push(zoom); }
                else {
                  state.autoModes.push(`${name}:${value}`);
                  if (options.auto === 'failed') throw new DOMException('unsupported', 'OverconstrainedError');
                }
              }
            }
          } });
        }
        const originalStop = track.stop.bind(track);
        Object.defineProperty(track, 'stop', {
          configurable: true,
          value: () => {
            state.stoppedTracks += 1;
            originalStop();
          },
        });
      }
      return stream;
    };

    Object.defineProperty(window, '__cameraGuideTest', {
      configurable: true,
      value: state,
    });
    Object.defineProperty(window, 'ImageCapture', { configurable: true, value: options.still ? class {
      async getPhotoCapabilities() { return { imageWidth: { max: 1600 }, imageHeight: { max: 1200 } }; }
      async takePhoto(settings?: unknown) {
        state.photoCalls += 1;
        if (options.still === 'failed') throw new DOMException('unsupported', 'NotSupportedError');
        if ((options.still === 'default-only' || options.still === 'oversized') && settings) throw new DOMException('photo size unsupported', 'NotSupportedError');
        const photo = document.createElement('canvas');
        photo.width = options.still === 'oversized' ? 10001 : 1600;
        photo.height = options.still === 'oversized' ? 1 : 1200;
        photo.getContext('2d')!.fillRect(0, 0, 1600, 1200);
        const blob = await new Promise<Blob>((resolve) => photo.toBlob((value) => resolve(value!), 'image/png'));
        state.photoBlob = blob;
        return blob;
      }
    } : undefined });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: () => {
          state.requests += 1;
          if (nextResponse === 'denied') {
            return Promise.reject(new DOMException('permission denied', 'NotAllowedError'));
          }
          if (nextResponse === 'pending') {
            const stream = createTrackedStream();
            state.stream = stream;
            return new Promise<MediaStream>((resolve) => {
              state.resolve = resolve;
            });
          }
          return Promise.resolve(createTrackedStream());
        },
      },
    });
  }, { nextResponse: response, options });
}

async function openDocumentUpload(page: Page) {
  await page.goto('/document-upload');
  await expect(page.getByRole('button', { name: '촬영하기', exact: true })).toBeVisible();
}

async function expectLandscapeGuide(page: Page) {
  const guide = await page.getByTestId('camera-capture-guide').boundingBox();
  const video = await page.getByLabel('실시간 카메라').evaluate((element: HTMLVideoElement) => {
    const box = element.getBoundingClientRect();
    const scale = Math.min(box.width / element.videoWidth, box.height / element.videoHeight);
    const width = element.videoWidth * scale;
    const height = element.videoHeight * scale;
    return { x: box.x + (box.width - width) / 2, y: box.y + (box.height - height) / 2, width, height };
  });
  expect(guide).not.toBeNull();
  expect(guide!.width / guide!.height).toBeCloseTo(4 / 3, 2);
  expect(guide!.x).toBeGreaterThanOrEqual(video.x - 1);
  expect(guide!.y).toBeGreaterThanOrEqual(video.y - 1);
  expect(guide!.x + guide!.width).toBeLessThanOrEqual(video.x + video.width + 1);
  expect(guide!.y + guide!.height).toBeLessThanOrEqual(video.y + video.height + 1);
}

test('지원되는 보안 컨텍스트에서 카메라를 열어 촬영한 JPEG 미리보기를 보여주고 스트림을 닫는다', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await installCamera(page, 'ready');
  await openDocumentUpload(page);

  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  const video = dialog.getByLabel('실시간 카메라');
  await expect(dialog).toBeVisible();
  await expect(video).toBeVisible();
  await expect(dialog.getByRole('button', { name: '사진 촬영' })).toBeEnabled();
  const requestedStreams = await page.evaluate(() => window.__cameraGuideTest.requests);
  expect(requestedStreams).toBeGreaterThanOrEqual(1);
  await expectLandscapeGuide(page);
  await dialog.screenshot({ path: testInfo.outputPath('guided-camera-mobile.png') });

  await page.setViewportSize({ width: 844, height: 390 });
  const shutter = dialog.getByRole('button', { name: '사진 촬영' });
  await shutter.scrollIntoViewIfNeeded();
  await expect(shutter).toBeVisible();
  const shutterBox = await shutter.boundingBox();
  expect(shutterBox).not.toBeNull();
  expect(shutterBox!.y).toBeGreaterThanOrEqual(0);
  expect(shutterBox!.y + shutterBox!.height).toBeLessThanOrEqual(390);
  await expectLandscapeGuide(page);
  await dialog.screenshot({ path: testInfo.outputPath('guided-camera-short-landscape.png') });

  const guideBox = await dialog.getByTestId('camera-capture-guide').boundingBox();
  const videoBox = await video.boundingBox();
  expect(guideBox).not.toBeNull();
  expect(videoBox).not.toBeNull();
  const expectedSize = [720, 960];
  await shutter.click();

  const preview = page.getByRole('img', { name: '선택한 약봉투 미리보기' });
  await expect(preview).toBeVisible();
  await expect(page.getByText(/\.jpg\s*·/)).toBeVisible();
  await expect.poll(() => preview.evaluate((image) => [image.naturalWidth, image.naturalHeight])).toEqual(expectedSize);
  await page.screenshot({ path: testInfo.outputPath('landscape-capture-preview.png'), fullPage: true });
  await expect(dialog).toBeHidden();
  await expect.poll(() => page.evaluate(() => window.__cameraGuideTest.stoppedTracks)).toBe(requestedStreams);
});

test('모바일 촬영하기는 가이드를 열고 그 안에서 일반 카메라로 전환한다', async ({ page }, testInfo) => {
  await installCamera(page, 'ready');
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'maxTouchPoints', { configurable: true, value: 5 });
    const matchMedia = window.matchMedia.bind(window);
    window.matchMedia = (query) => {
      const result = matchMedia(query);
      if (query === '(pointer: coarse)') Object.defineProperty(result, 'matches', { value: true });
      return result;
    };
  });
  await openDocumentUpload(page);
  await expect(page.getByRole('button', { name: '촬영하기', exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: '사진 촬영', exact: true })).toBeEnabled();
  await dialog.screenshot({ path: testInfo.outputPath('unified-mobile-camera.png') });
  const chooserPromise = page.waitForEvent('filechooser');
  await dialog.getByRole('button', { name: '일반 카메라로 전환', exact: true }).click();
  const chooser = await chooserPromise;
  expect(await chooser.element().getAttribute('capture')).toBe('environment');
  await expect(dialog).toBeHidden();
  const state = await page.evaluate(() => ({ stopped: window.__cameraGuideTest.stoppedTracks, opened: window.__cameraGuideTest.requests }));
  expect(state.opened).toBeGreaterThan(0);
  expect(state.stopped).toBe(state.opened);
  await page.screenshot({ path: testInfo.outputPath('unified-upload-page.png'), fullPage: true });
});

test('지원 기기의 실제 배율을 변경하고 정지 사진 원본을 재인코딩 없이 보존한다', async ({ page }, testInfo) => {
  await installCamera(page, 'ready', { zoom: true, still: 'ready' });
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  const zoom = dialog.getByRole('slider', { name: '촬영 배율' });
  await expect(zoom).toBeEnabled();
  await zoom.fill('2');
  await expect.poll(() => page.evaluate(() => window.__cameraGuideTest.zoomValues)).toEqual([2]);
  await expect(dialog.getByText('2.0×', { exact: true })).toBeVisible();
  const nativeButton = await dialog.getByRole('button', { name: '일반 카메라로 전환' }).boundingBox();
  expect(nativeButton!.y + nativeButton!.height).toBeLessThanOrEqual(812);
  await dialog.screenshot({ path: testInfo.outputPath('camera-zoom-mobile.png') });
  await dialog.getByRole('button', { name: '사진 촬영' }).click();
  const preview = page.getByRole('img', { name: '선택한 약봉투 미리보기' });
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((image) => [image.naturalWidth, image.naturalHeight])).toEqual([1600, 1200]);
  expect(await preview.evaluate(async (image) => {
    const saved = await (await fetch(image.src)).blob();
    const original = window.__cameraGuideTest.photoBlob!;
    const originalBytes = new Uint8Array(await original.arrayBuffer());
    return saved.type === original.type && saved.size === original.size
      && new Uint8Array(await saved.arrayBuffer()).every((value, index) => value === originalBytes[index]);
  })).toBe(true);
});

test('정지 사진 촬영을 지원하지 않으면 영상 전체 해상도로 저장한다', async ({ page }) => {
  await installCamera(page, 'ready', { still: 'failed' });
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  await expect(dialog.getByText('배율 조절은 기본 카메라에서 이용해주세요.')).toBeVisible();
  await dialog.getByRole('button', { name: '사진 촬영' }).click();
  const preview = page.getByRole('img', { name: '선택한 약봉투 미리보기' });
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((image) => [image.naturalWidth, image.naturalHeight])).toEqual([720, 960]);
  expect(await page.evaluate(() => window.__cameraGuideTest.photoCalls)).toBe(2);
});

for (const auto of ['ready', 'failed'] as const) {
  test(`자동 초점·노출은 지원 모드만 요청하고 설정 거절 시에도 촬영된다 (${auto})`, async ({ page }) => {
    await installCamera(page, 'ready', { auto });
    await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
    const shutter = page.getByRole('button', { name: '사진 촬영', exact: true });
    await expect(shutter).toBeEnabled();
    expect(await page.evaluate(() => window.__cameraGuideTest.autoModes)).toEqual(['focusMode:continuous', 'exposureMode:continuous']);
    await expect(page.getByText('미리보기 해상도가 낮아요.', { exact: false })).toBeVisible();
    await shutter.click();
    await expect(page.getByRole('img', { name: '선택한 약봉투 미리보기' })).toBeVisible();
  });
}

test('고해상도 설정이 거절되면 기본 정지 사진으로 재시도하고 원본 크기를 유지한다', async ({ page }) => {
  await installCamera(page, 'ready', { still: 'default-only' });
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  await page.getByRole('button', { name: '사진 촬영', exact: true }).click();
  const preview = page.getByRole('img', { name: '선택한 약봉투 미리보기' });
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((image) => [image.naturalWidth, image.naturalHeight])).toEqual([1600, 1200]);
  expect(await page.evaluate(() => window.__cameraGuideTest.photoCalls)).toBe(2);
});

test('배율 변경 직후에는 안정화 시간을 확보하고 닫으면 스트림을 정리한다', async ({ page }) => {
  await installCamera(page, 'ready', { zoom: true });
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const shutter = page.getByRole('button', { name: '사진 촬영', exact: true });
  await expect(shutter).toBeEnabled();
  await page.clock.install();
  await page.getByRole('slider', { name: '촬영 배율' }).fill('2');
  await expect(shutter).toBeDisabled();
  await page.clock.fastForward(700);
  await expect(shutter).toBeEnabled();
  await page.getByRole('slider', { name: '촬영 배율' }).fill('3');
  await page.getByRole('button', { name: '카메라 닫기' }).click();
  await page.clock.fastForward(1000);
  await expect(page.getByRole('dialog')).toBeHidden();
  const state = await page.evaluate(() => ({ stopped: window.__cameraGuideTest.stoppedTracks, opened: window.__cameraGuideTest.requests }));
  expect(state.opened).toBeGreaterThan(0);
  expect(state.stopped).toBe(state.opened);
});

test('기본 정지 사진이 서버 크기 한도를 넘으면 업로드 가능한 전체 영상으로 대체한다', async ({ page }) => {
  await installCamera(page, 'ready', { still: 'oversized' });
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  await page.getByRole('button', { name: '사진 촬영', exact: true }).click();
  const preview = page.getByRole('img', { name: '선택한 약봉투 미리보기' });
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((image) => [image.naturalWidth, image.naturalHeight])).toEqual([720, 960]);
});

test('보안 컨텍스트가 아니면 안내 카메라 대신 기존 기본 카메라 파일 선택기를 연다', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false });
  });
  await openDocumentUpload(page);

  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const chooser = await chooserPromise;

  await expect(page.getByRole('dialog', { name: '약봉투 촬영' })).toHaveCount(0);
  expect(await chooser.element().getAttribute('capture')).toBe('environment');
  expect(await chooser.element().getAttribute('accept')).toMatch(/image\/jpeg,image\/png,image\/heic,image\/heif/);
});

test('카메라 권한을 거부하면 오류와 두 가지 대체 수단을 안내한다', async ({ page }) => {
  await installCamera(page, 'denied');
  await openDocumentUpload(page);

  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('alert')).toContainText('카메라 권한을 허용해주세요');
  await expect(dialog.getByRole('button', { name: '일반 카메라로 전환' })).toBeVisible();
  await expect(dialog.getByRole('button', { name: '사진에서 선택' })).toBeVisible();
});

test('카메라 요청이 늦게 허용되어도 닫힌 안내창의 스트림을 즉시 정리한다', async ({ page }) => {
  await installCamera(page, 'pending');
  await openDocumentUpload(page);

  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  await expect(dialog).toBeVisible();
  await expect.poll(() => page.evaluate(() => Boolean(window.__cameraGuideTest.resolve))).toBe(true);

  await dialog.getByRole('button', { name: '카메라 닫기' }).click();
  await expect(dialog).toBeHidden();
  await page.evaluate(() => {
    const state = window.__cameraGuideTest;
    if (!state.stream) throw new Error('Expected a pending fake camera stream');
    state.resolve?.(state.stream);
  });

  await expect.poll(() => page.evaluate(() => window.__cameraGuideTest.stoppedTracks)).toBe(1);
});

for (const supported of [true, false]) {
  test(`가로 촬영 전환은 화면 잠금 지원 여부에 맞게 처리한다 (${supported})`, async ({ page }) => {
    await installCamera(page, 'ready');
    await page.addInitScript((canLock) => {
      const calls: string[] = [];
      Object.defineProperty(window, '__rotationCalls', { value: calls });
      let fullscreen: Element | null = null;
      Object.defineProperty(document, 'fullscreenElement', { get: () => fullscreen });
      Element.prototype.requestFullscreen = async () => {
        fullscreen = document.documentElement;
        calls.push('fullscreen');
      };
      document.exitFullscreen = async () => { fullscreen = null; calls.push('exit'); };
      Object.defineProperty(screen.orientation, 'lock', { configurable: true, value: async (direction: string) => {
        calls.push(direction);
        if (!canLock) throw new DOMException('not supported', 'NotSupportedError');
      } });
      screen.orientation.unlock = () => { calls.push('unlock'); };
    }, supported);
    await openDocumentUpload(page);
    await page.getByRole('button', { name: '촬영하기', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
    await dialog.getByRole('button', { name: '가로 촬영으로 전환' }).click();
    await expect(dialog.getByRole('button', { name: '자동 회전으로 돌아가기' })).toBeEnabled();
    if (!supported) await expect(dialog.getByText(/이 브라우저는 자동 전환을 지원하지 않아요/)).toBeVisible();
    await dialog.getByRole('button', { name: '카메라 닫기' }).click();
    const calls = await page.evaluate(() => (window as Window & { __rotationCalls: string[] }).__rotationCalls);
    expect(calls).toEqual(supported ? ['fullscreen', 'landscape', 'unlock', 'exit'] : ['fullscreen', 'landscape', 'exit']);
  });
}

declare global {
  interface Window {
    __cameraGuideTest: {
      requests: number;
      stoppedTracks: number;
      resolve?: (stream: MediaStream) => void;
      stream?: MediaStream;
      zoomValues: number[];
      photoCalls: number;
      autoModes: string[];
      photoBlob?: Blob;
    };
  }
}
