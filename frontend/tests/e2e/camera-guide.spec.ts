import { expect, test, type Locator, type Page } from 'playwright/test';

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

async function installCamera(page: Page, response: CameraResponse, options: { zoom?: boolean; still?: 'ready' | 'failed' | 'default-only' | 'oversized'; auto?: 'ready' | 'failed'; streamSize?: { width: number; height: number } } = {}) {
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
      // Lets a test simulate a device rotation reporting new intrinsic dimensions on the SAME live
      // track (no new getUserMedia call, no new `playing` event) — set once the stream is created.
      resizeStream: undefined as undefined | ((width: number, height: number) => void),
    };

    const drawPlaceholder = (canvas: HTMLCanvasElement, width: number, height: number) => {
      const context = canvas.getContext('2d');
      if (!context) return;
      // A centered "document" placeholder, sized proportionally so it looks sensible at any stream aspect.
      const docWidth = width * 0.67;
      const docHeight = height * 0.8;
      const docX = (width - docWidth) / 2;
      const docY = (height - docHeight) / 2;
      context.fillStyle = '#cbd5e1';
      context.fillRect(0, 0, width, height);
      context.fillStyle = '#ffffff';
      context.fillRect(docX, docY, docWidth, docHeight);
      context.fillStyle = '#94a3b8';
      const lineHeight = docHeight / 11;
      for (let line = 0; line < 8; line += 1) {
        context.fillRect(docX + docWidth * 0.125, docY + lineHeight * (1.4 + line), docWidth * 0.75, lineHeight * 0.35);
      }
    };

    const createTrackedStream = () => {
      const canvas = document.createElement('canvas');
      const { width, height } = options.streamSize ?? { width: 720, height: 960 };
      canvas.width = width;
      canvas.height = height;
      drawPlaceholder(canvas, width, height);
      state.resizeStream = (nextWidth, nextHeight) => {
        canvas.width = nextWidth;
        canvas.height = nextHeight;
        drawPlaceholder(canvas, nextWidth, nextHeight);
      };
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

async function getVideoBox(page: Page) {
  return page.getByLabel('실시간 카메라').evaluate((element: HTMLVideoElement) => {
    const box = element.getBoundingClientRect();
    const scale = Math.min(box.width / element.videoWidth, box.height / element.videoHeight);
    const width = element.videoWidth * scale;
    const height = element.videoHeight * scale;
    return { x: box.x + (box.width - width) / 2, y: box.y + (box.height - height) / 2, width, height };
  });
}

// 가이드는 고정된 문서 비율이 아니라 실시간 영상 자체의 비율을 따르고, 각 변에서 4~8%(목표 6%) 안쪽에 위치해야 한다.
async function expectGuideMatchesVideo(page: Page) {
  const guide = await page.getByTestId('camera-capture-guide').boundingBox();
  const video = await getVideoBox(page);
  expect(guide).not.toBeNull();
  expect(guide!.width / guide!.height).toBeCloseTo(video.width / video.height, 2);
  const insetXRatio = (video.width - guide!.width) / 2 / video.width;
  const insetYRatio = (video.height - guide!.height) / 2 / video.height;
  expect(insetXRatio).toBeGreaterThanOrEqual(0.04);
  expect(insetXRatio).toBeLessThanOrEqual(0.08);
  expect(insetYRatio).toBeGreaterThanOrEqual(0.04);
  expect(insetYRatio).toBeLessThanOrEqual(0.08);
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
  await expectGuideMatchesVideo(page);
  await dialog.screenshot({ path: testInfo.outputPath('guided-camera-mobile.png') });

  await page.setViewportSize({ width: 844, height: 390 });
  const shutter = dialog.getByRole('button', { name: '사진 촬영' });
  await shutter.scrollIntoViewIfNeeded();
  await expect(shutter).toBeVisible();
  const shutterBox = await shutter.boundingBox();
  expect(shutterBox).not.toBeNull();
  expect(shutterBox!.y).toBeGreaterThanOrEqual(0);
  expect(shutterBox!.y + shutterBox!.height).toBeLessThanOrEqual(390);
  await expectGuideMatchesVideo(page);
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

// Waits until the guide's own on-screen ratio agrees with the video's on-screen ratio AND both have
// converged on the target aspect. A plain single-shot equality check right after triggering a stream
// resize is flaky here: intrinsic videoWidth/videoHeight on a MediaStream-sourced <video> can pass
// through transient/intermediate readings for a few frames before settling (observed directly against
// this browser build), so a loose one-off inequality can match on a not-yet-settled frame.
async function waitForGuideToMatchAspect(page: Page, targetAspect: number) {
  await expect.poll(async () => {
    const guide = await page.getByTestId('camera-capture-guide').boundingBox();
    const video = await getVideoBox(page);
    if (!guide || video.width <= 0 || video.height <= 0) return false;
    const guideAspect = guide.width / guide.height;
    const videoAspect = video.width / video.height;
    return Math.abs(guideAspect - videoAspect) < 0.02 && Math.abs(videoAspect - targetAspect) < 0.05;
  }).toBe(true);
}

// document.documentElement.requestFullscreen always rejects, so clicking the rotate toggle deterministically
// falls through to the long fallback rotation hint (the worst case for available vertical space) instead of
// racing real Fullscreen/Screen-Orientation API timing.
async function forceRotationFallback(page: Page) {
  await page.addInitScript(() => {
    Element.prototype.requestFullscreen = () => Promise.reject(new DOMException('denied', 'NotAllowedError'));
  });
}

async function expectControlsFullyVisible(dialog: Locator, viewport: { width: number; height: number }) {
  const shutter = dialog.getByRole('button', { name: '사진 촬영' });
  const closeButton = dialog.getByRole('button', { name: '카메라 닫기' });
  const rotateToggle = dialog.getByTestId('camera-rotate-toggle');
  const nativeButton = dialog.getByRole('button', { name: '일반 카메라로 전환' });
  const galleryButton = dialog.getByRole('button', { name: '사진에서 선택' });
  for (const control of [shutter, closeButton, rotateToggle, nativeButton, galleryButton]) {
    await expect(control).toBeVisible();
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
  }
}

test('세로 방향에서 실시간 미리보기가 화면 대부분을 차지하고, 배율 조절과 회전 안내가 함께 떠도 조작부가 잘리지 않는다', async ({ page }, testInfo) => {
  const viewport = { width: 375, height: 812 };
  await page.setViewportSize(viewport);
  await forceRotationFallback(page);
  await installCamera(page, 'ready', { zoom: true });
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  const video = dialog.getByLabel('실시간 카메라');
  await expect(video).toBeVisible();
  const shutter = dialog.getByRole('button', { name: '사진 촬영' });
  await expect(shutter).toBeEnabled(); // settled: the settle-timer message is gone, layout has reached steady state.

  // The allocated preview area (not the letterboxed pixels, which depend on the camera's own aspect
  // ratio and must not be cropped) reflects what our layout controls.
  const frameBox = await dialog.getByTestId('camera-preview-frame').boundingBox();
  expect(frameBox).not.toBeNull();
  expect(frameBox!.height / viewport.height).toBeGreaterThanOrEqual(0.5);
  expect(frameBox!.width / viewport.width).toBeGreaterThanOrEqual(0.85);
  await expectGuideMatchesVideo(page);
  await expectControlsFullyVisible(dialog, viewport);

  const guidance = dialog.getByTestId('camera-guidance');
  await expect(guidance).toHaveCount(1);
  await expect(guidance).toBeVisible();
  const guidanceBox = await guidance.boundingBox();
  expect(guidanceBox).not.toBeNull();
  expect(guidanceBox!.y).toBeGreaterThanOrEqual(frameBox!.y + frameBox!.height - 1);

  await dialog.screenshot({ path: testInfo.outputPath('portrait-preview-dominant.png') });

  // Worst case: zoom slider + the long rotation-hint fallback text both showing at once.
  await dialog.getByTestId('camera-rotate-toggle').click();
  await expect(dialog.getByText('이 브라우저는 자동 전환을 지원하지 않아요', { exact: false })).toBeVisible();
  await expectControlsFullyVisible(dialog, viewport);
  await dialog.screenshot({ path: testInfo.outputPath('portrait-rotation-hint.png') });
});

test('가로 방향에서는 제목이 상단 행을 차지하지 않고, 배율 조절과 회전 안내가 함께 떠도 조작부가 잘리지 않는다', async ({ page }, testInfo) => {
  const viewport = { width: 844, height: 390 };
  await page.setViewportSize(viewport);
  await forceRotationFallback(page);
  // A realistic landscape-shaped stream (16:9), not just the portrait 720x960 fixture used elsewhere.
  await installCamera(page, 'ready', { zoom: true, streamSize: { width: 1280, height: 720 } });
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  const video = dialog.getByLabel('실시간 카메라');
  await expect(video).toBeVisible();
  const shutter = dialog.getByRole('button', { name: '사진 촬영' });
  await expect(shutter).toBeEnabled(); // settled: the settle-timer message is gone, layout has reached steady state.

  // The allocated preview column (not the letterboxed pixels, which follow the camera's own aspect
  // ratio and must not be cropped) reflects what our layout controls.
  const frameBox = await dialog.getByTestId('camera-preview-frame').boundingBox();
  expect(frameBox).not.toBeNull();
  expect(frameBox!.width / viewport.width).toBeGreaterThanOrEqual(0.6);
  // The title row must not reserve top space in landscape: the preview column starts right after the
  // safe-area padding (8px), not after a ~44px+ title/close-button row.
  expect(frameBox!.y).toBeLessThanOrEqual(10);
  await expectGuideMatchesVideo(page);
  await expectControlsFullyVisible(dialog, viewport);

  // The title is still present for a11y (sr-only), but must not occupy visible top-row space in landscape.
  const titleBox = await dialog.getByText('약봉투 촬영', { exact: true }).boundingBox();
  expect(titleBox).not.toBeNull();
  expect(titleBox!.width).toBeLessThanOrEqual(2);
  expect(titleBox!.height).toBeLessThanOrEqual(2);

  // The <output> zoom readout also carries an implicit role=status, so we must target the guidance
  // paragraph by its own test id rather than counting every role=status node in the dialog.
  const guidance = dialog.getByTestId('camera-guidance');
  await expect(guidance).toHaveCount(1);
  const guidanceBox = await guidance.boundingBox();
  expect(guidanceBox).not.toBeNull();
  // Guidance lives in the side control column, not overlapping the preview column.
  expect(guidanceBox!.x).toBeGreaterThanOrEqual(frameBox!.x + frameBox!.width - 1);

  await dialog.screenshot({ path: testInfo.outputPath('landscape-preview-dominant.png') });

  // Worst case: zoom slider + the long rotation-hint fallback text both showing at once, in the
  // narrowest (390px-tall) landscape column budget.
  await dialog.getByTestId('camera-rotate-toggle').click();
  await expect(dialog.getByText('이 브라우저는 자동 전환을 지원하지 않아요', { exact: false })).toBeVisible();
  await expectControlsFullyVisible(dialog, viewport);
  await dialog.screenshot({ path: testInfo.outputPath('landscape-rotation-hint.png') });
});

test('실시간 스트림의 고유 크기가 재생 이벤트 없이 세로에서 가로로(그리고 다시 반대로) 바뀌어도 가이드가 갱신되고, 조작부는 상단에 몰리지 않으며 잘리지 않는다', async ({ page }, testInfo) => {
  const viewport = { width: 900, height: 500 }; // tall enough landscape column to expose top-packing
  await page.setViewportSize(viewport);
  await installCamera(page, 'ready'); // starts portrait-shaped (720x960), the default fixture stream
  await openDocumentUpload(page);
  await page.getByRole('button', { name: '촬영하기', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '약봉투 촬영' });
  const video = dialog.getByLabel('실시간 카메라');
  await expect(video).toBeVisible();
  const shutter = dialog.getByRole('button', { name: '사진 촬영' });
  await expect(shutter).toBeEnabled();

  // Baseline: guide follows the initial portrait-shaped stream.
  await expectGuideMatchesVideo(page);
  const initialVideo = await getVideoBox(page);
  expect(initialVideo.width).toBeLessThan(initialVideo.height);

  // Simulate a device rotation that changes the SAME live track's intrinsic size to a realistic 4:3
  // landscape frame WITHOUT a new getUserMedia call or a new `playing` event — the exact case the
  // stale-videoAspect bug missed (it only ever read dimensions once, at the first `playing`).
  await page.evaluate(() => window.__cameraGuideTest.resizeStream?.(1024, 768));
  await waitForGuideToMatchAspect(page, 1024 / 768);
  await expectGuideMatchesVideo(page);
  const landscapeVideo = await getVideoBox(page);
  expect(landscapeVideo.width / landscapeVideo.height).toBeCloseTo(1024 / 768, 1);

  // Controls must not be clipped, and must be spread across the column instead of stuck at the top
  // with a large blank gap below (the second bug from the same report).
  await expectControlsFullyVisible(dialog, viewport);
  const controlsBox = await dialog.getByTestId('camera-controls').boundingBox();
  expect(controlsBox).not.toBeNull();
  const shutterBox = await shutter.boundingBox();
  expect(shutterBox).not.toBeNull();
  const relativeShutterCenter = (shutterBox!.y + shutterBox!.height / 2 - controlsBox!.y) / controlsBox!.height;
  expect(relativeShutterCenter).toBeGreaterThan(0.25);
  expect(relativeShutterCenter).toBeLessThan(0.75);
  const galleryBox = await dialog.getByRole('button', { name: '사진에서 선택' }).boundingBox();
  expect(galleryBox).not.toBeNull();
  const relativeGalleryBottom = (galleryBox!.y + galleryBox!.height - controlsBox!.y) / controlsBox!.height;
  expect(relativeGalleryBottom).toBeGreaterThan(0.6);

  await dialog.screenshot({ path: testInfo.outputPath('landscape-dynamic-resize.png') });

  // Reverse: rotate back to a portrait-shaped stream and confirm the guide tracks it back too, on the
  // same live track, again without any new `playing` event.
  await page.evaluate(() => window.__cameraGuideTest.resizeStream?.(720, 960));
  await waitForGuideToMatchAspect(page, 720 / 960);
  await expectGuideMatchesVideo(page);
});

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
      resizeStream?: (width: number, height: number) => void;
    };
  }
}
