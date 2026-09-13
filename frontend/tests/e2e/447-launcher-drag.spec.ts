import { expect, test, type Locator, type Page, type TestInfo } from 'playwright/test';
import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

const launcherPositionKey = 'rxvita.chat-launcher-position.v1';

async function dragLauncher(page: Page, launcher: Locator, target: { x: number; y: number }) {
  await launcher.hover();
  const start = (await launcher.boundingBox())!;
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x, target.y, { steps: 6 });
  await page.mouse.up();
}

async function launcherGeometry(launcher: Locator) {
  const box = (await launcher.boundingBox())!;
  const tailOverflow = await launcher.evaluate((element) => {
    const bottom = Number.parseFloat(getComputedStyle(element, '::after').bottom);
    return Number.isFinite(bottom) ? Math.max(0, -bottom) : 0;
  });
  return { ...box, tailOverflow };
}

async function expectLauncherInsideCurrentBounds(page: Page, launcher: Locator) {
  const box = await launcherGeometry(launcher);
  const bounds = await page.evaluate(() => {
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft ?? 0;
    const top = viewport?.offsetTop ?? 0;
    const width = viewport?.width ?? window.innerWidth;
    const height = viewport?.height ?? window.innerHeight;
    const nav = document.querySelector<HTMLElement>("nav[aria-label='주요 화면']");
    const navBox = nav?.getBoundingClientRect();
    const visibleNavTop = navBox && navBox.width > 0 && navBox.height > 0
      ? navBox.top
      : Number.POSITIVE_INFINITY;
    return { left, top, right: left + width, bottom: Math.min(top + height, visibleNavTop) };
  });
  expect(box.x).toBeGreaterThanOrEqual(bounds.left + 15.5);
  expect(box.y).toBeGreaterThanOrEqual(bounds.top + 15.5);
  expect(box.x + box.width).toBeLessThanOrEqual(bounds.right - 15.5);
  expect(box.y + box.height + box.tailOverflow).toBeLessThanOrEqual(bounds.bottom - 15.5);
}

async function dismissGuestPrompt(page: Page) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: '다음에 할게요' }).click();
  await expect(dialog).toHaveCount(0);
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript((key) => {
    const cleanMarker = `${key}.test-clean`;
    if (sessionStorage.getItem(cleanMarker) === null) {
      localStorage.removeItem(key);
      sessionStorage.setItem(cleanMarker, '1');
    }
  }, launcherPositionKey);
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: {} }));
});

test('MY launcher stays at a freely dropped interior point without activating chat', async ({ page }, testInfo: TestInfo) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dev/my-authenticated', { waitUntil: 'domcontentloaded' });
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });
  const schedule = page.getByRole('switch', { name: '일정 알림', exact: true });
  await expect(launcher).toBeVisible();
  await expect(schedule).toBeVisible();

  const scheduleBox = (await schedule.boundingBox())!;
  const centerOwnerBefore = await page.evaluate(({ x, y }) => {
    const element = document.elementFromPoint(x, y);
    return element?.closest('button')?.getAttribute('aria-label') ?? null;
  }, { x: scheduleBox.x + scheduleBox.width / 2, y: scheduleBox.y + scheduleBox.height / 2 });
  expect(centerOwnerBefore).toBe('챗봇');

  await dragLauncher(page, launcher, { x: 154, y: 290 });
  await page.mouse.move(8, 8);

  const dropped = (await launcher.boundingBox())!;
  expect(dropped.x).toBeGreaterThan(100);
  expect(dropped.x).toBeLessThan(160);
  expect(dropped.y).toBeGreaterThan(240);
  expect(dropped.y).toBeLessThan(300);
  expect(dropped.x).toBeGreaterThan(16);
  expect(dropped.x + dropped.width).toBeLessThan(374);
  const centerOwnerAfter = await page.evaluate(({ x, y }) => {
    const element = document.elementFromPoint(x, y);
    return element?.closest('[role="switch"]')?.getAttribute('aria-label') ?? null;
  }, { x: scheduleBox.x + scheduleBox.width / 2, y: scheduleBox.y + scheduleBox.height / 2 });
  expect(centerOwnerAfter).toBe('일정 알림');
  await expect(page).toHaveURL(/\/dev\/my-authenticated$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('task-7-free-placement-390.png') });
});

test('free position persists across reload and tab/non-tab routes without snapping', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/home', { waitUntil: 'domcontentloaded' });
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });
  await dragLauncher(page, launcher, { x: 174, y: 330 });
  await page.mouse.move(8, 8);
  const chosen = (await launcher.boundingBox())!;
  expect(chosen.x).toBeGreaterThan(110);
  expect(chosen.x).toBeLessThan(160);
  expect(chosen.y).toBeGreaterThan(270);
  expect(chosen.y).toBeLessThan(330);
  expect(await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? 'null'), launcherPositionKey))
    .toEqual({ left: Math.round(chosen.x), top: Math.round(chosen.y) });

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.mouse.move(8, 8);
  await expect(page.getByRole('button', { name: '챗봇', exact: true })).toBeVisible();
  let restored = (await page.getByRole('button', { name: '챗봇', exact: true }).boundingBox())!;
  expect(restored.x).toBeCloseTo(chosen.x, 0);
  expect(restored.y).toBeCloseTo(chosen.y, 0);

  await page.goto('/terms', { waitUntil: 'domcontentloaded' });
  await page.mouse.move(8, 8);
  restored = (await page.getByRole('button', { name: '챗봇', exact: true }).boundingBox())!;
  expect(restored.x).toBeCloseTo(chosen.x, 0);
  expect(restored.y).toBeCloseTo(chosen.y, 0);
  expect(await page.getByRole('navigation', { name: '주요 화면' }).count()).toBe(0);

  await page.goto('/home', { waitUntil: 'domcontentloaded' });
  await page.mouse.move(8, 8);
  restored = (await page.getByRole('button', { name: '챗봇', exact: true }).boundingBox())!;
  expect(restored.x).toBeCloseTo(chosen.x, 0);
  expect(restored.y).toBeCloseTo(chosen.y, 0);
});

test('all edges clamp above actual navigation and a narrow viewport restores the preferred position when expanded', async ({ page }, testInfo: TestInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/home', { waitUntil: 'domcontentloaded' });
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });

  await dragLauncher(page, launcher, { x: 1, y: 1 });
  await page.mouse.move(200, 400);
  let box = (await launcher.boundingBox())!;
  expect(box.x).toBeCloseTo(16, 0);
  expect(box.y).toBeCloseTo(16, 0);

  await dragLauncher(page, launcher, { x: 389, y: 843 });
  await page.mouse.move(8, 8);
  await expectLauncherInsideCurrentBounds(page, launcher);
  box = (await launcher.boundingBox())!;
  expect(box.x + box.width).toBeCloseTo(374, 0);

  await dragLauncher(page, launcher, { x: 310, y: 360 });
  await page.mouse.move(8, 8);
  const preferred = (await launcher.boundingBox())!;
  const savedBeforeResize = await page.evaluate((key) => localStorage.getItem(key), launcherPositionKey);
  expect(preferred.x).toBeGreaterThan(260);

  await page.setViewportSize({ width: 320, height: 700 });
  await expect.poll(async () => (await launcher.boundingBox())!.x).toBeLessThanOrEqual(244.5);
  await expectLauncherInsideCurrentBounds(page, launcher);
  expect(await page.evaluate((key) => localStorage.getItem(key), launcherPositionKey)).toBe(savedBeforeResize);
  await page.screenshot({ path: testInfo.outputPath('task-7-bounds-320.png') });

  await page.setViewportSize({ width: 1280, height: 844 });
  await page.mouse.move(8, 8);
  await expect.poll(async () => (await launcher.boundingBox())!.x).toBeCloseTo(preferred.x, 0);
  await expectLauncherInsideCurrentBounds(page, launcher);
});

test('under-threshold pointer movement and keyboard Enter/Space keep the guest action while drag suppresses only its generated click', async ({ page }) => {
  await page.goto('/home', { waitUntil: 'domcontentloaded' });
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });
  const start = (await launcher.boundingBox())!;
  await page.mouse.move(start.x + 30, start.y + 30);
  await page.mouse.down();
  await page.mouse.move(start.x + 34, start.y + 30);
  await page.mouse.up();
  await dismissGuestPrompt(page);

  await dragLauncher(page, launcher, { x: 140, y: 260 });
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await launcher.focus();
  await page.keyboard.press('Enter');
  await dismissGuestPrompt(page);
  await launcher.focus();
  await page.keyboard.press('Space');
  await dismissGuestPrompt(page);
});

test('authenticated normal click still navigates to chat after a stored position is applied', async ({ page }) => {
  await page.addInitScript(({ key }) => {
    localStorage.setItem(key, JSON.stringify({ left: 120, top: 220 }));
    sessionStorage.setItem('poke.access-token', 'issue447-launcher-fixture');
    sessionStorage.setItem('poke.account-principal', 'issue447-launcher@example.com');
  }, { key: launcherPositionKey });
  await page.goto('/home', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole('button', { name: '챗봇', exact: true })).toHaveCount(0);
});

test.describe('touch input', () => {
  test.use({ hasTouch: true });

  test('browser touch pointer events drag freely and a normal tap retains the guest action', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'CDP touch input is Chromium-specific.');
    await page.goto('/home', { waitUntil: 'domcontentloaded' });
    const launcher = page.getByRole('button', { name: '챗봇', exact: true });
    await launcher.evaluate((element) => {
      const testWindow = window as Window & { __launcherEvents?: string[] };
      testWindow.__launcherEvents = [];
      for (const type of ['pointerdown', 'pointerup', 'pointercancel', 'click']) {
        element.addEventListener(type, event => {
          const pointerType = event instanceof PointerEvent ? event.pointerType : 'click';
          testWindow.__launcherEvents?.push(`${type}:${pointerType}`);
        });
      }
    });
    const start = (await launcher.boundingBox())!;
    const session = await page.context().newCDPSession(page);
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x: start.x + 30, y: start.y + 30, id: 1, radiusX: 1, radiusY: 1, force: 1 }],
    });
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: 185, y: 350, id: 1, radiusX: 1, radiusY: 1, force: 1 }],
    });
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    const dropped = (await launcher.boundingBox())!;
    expect(dropped.x).toBeGreaterThan(130);
    expect(dropped.x).toBeLessThan(180);
    expect(await page.evaluate(() => (window as Window & { __launcherEvents?: string[] }).__launcherEvents))
      .toContain('pointerdown:touch');
    await expect(page.getByRole('dialog')).toHaveCount(0);

    await launcher.tap();
    await expect.poll(() => page.evaluate(() => (
      (window as Window & { __launcherEvents?: string[] }).__launcherEvents
        ?.filter(event => event === 'pointerdown:touch').length
    ))).toBe(2);
    await dismissGuestPrompt(page);

    // The pointerup fallback leaves one pointer-generated click suppressible on
    // browsers that synthesize it, while a new touch and keyboard remain actions.
    await launcher.evaluate(element => element.dispatchEvent(new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      detail: 1,
    })));
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await launcher.tap();
    await dismissGuestPrompt(page);
    await launcher.focus();
    await page.keyboard.press('Enter');
    await dismissGuestPrompt(page);
  });

  test('browser touch cancellation aborts movement without activation or persistence', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'CDP touch input is Chromium-specific.');
    await page.goto('/home', { waitUntil: 'domcontentloaded' });
    const launcher = page.getByRole('button', { name: '챗봇', exact: true });
    const start = (await launcher.boundingBox())!;
    const session = await page.context().newCDPSession(page);
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x: start.x + 30, y: start.y + 30, id: 1, radiusX: 1, radiusY: 1, force: 1 }],
    });
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: 175, y: 310, id: 1, radiusX: 1, radiusY: 1, force: 1 }],
    });
    await expect(launcher).toHaveClass(/is-dragging/);
    await session.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] });
    await expect(launcher).not.toHaveClass(/is-dragging/);
    const cancelled = (await launcher.boundingBox())!;
    expect(cancelled.x).toBeCloseTo(start.x, 0);
    expect(cancelled.y).toBeCloseTo(start.y, 0);
    expect(await page.evaluate((key) => localStorage.getItem(key), launcherPositionKey)).toBeNull();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});

test('lost pointer capture aborts an active drag and secondary mouse input is ignored', async ({ page }) => {
  await page.goto('/home', { waitUntil: 'domcontentloaded' });
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });
  await launcher.evaluate((element) => {
    element.addEventListener('pointerdown', event => {
      (window as Window & { __launcherPointerId?: number }).__launcherPointerId = event.pointerId;
    });
  });
  const start = (await launcher.boundingBox())!;
  await page.mouse.move(start.x + 30, start.y + 30);
  await page.mouse.down();
  await page.mouse.move(170, 300, { steps: 4 });
  await launcher.evaluate((element) => {
    const pointerId = (window as Window & { __launcherPointerId?: number }).__launcherPointerId;
    if (pointerId !== undefined) element.releasePointerCapture(pointerId);
  });
  await page.mouse.up();
  await page.mouse.move(8, 8);
  const aborted = (await launcher.boundingBox())!;
  expect(aborted.x).toBeCloseTo(start.x, 0);
  expect(aborted.y).toBeCloseTo(start.y, 0);
  expect(await page.evaluate((key) => localStorage.getItem(key), launcherPositionKey)).toBeNull();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await page.mouse.move(aborted.x + 30, aborted.y + 30);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(80, 120);
  await page.mouse.up({ button: 'right' });
  await page.mouse.move(8, 8);
  const afterSecondary = (await launcher.boundingBox())!;
  expect(afterSecondary.x).toBeCloseTo(aborted.x, 0);
  expect(afterSecondary.y).toBeCloseTo(aborted.y, 0);
  expect(await page.evaluate((key) => localStorage.getItem(key), launcherPositionKey)).toBeNull();
});

for (const scenario of ['invalid', 'read-denied', 'write-denied'] as const) {
  test(`storage ${scenario} falls back safely and leaves dragging functional`, async ({ page }) => {
    await page.addInitScript(({ key, mode }) => {
      if (mode === 'invalid') {
        localStorage.setItem(key, JSON.stringify({ left: Number.POSITIVE_INFINITY, top: 'bad' }));
        return;
      }
      const method = mode === 'read-denied' ? 'getItem' : 'setItem';
      const original = Storage.prototype[method];
      Object.defineProperty(Storage.prototype, method, {
        configurable: true,
        value(this: Storage, storageKey: string, ...args: string[]) {
          if (storageKey === key) throw new DOMException('blocked', 'SecurityError');
          return (original as (...values: string[]) => unknown).call(this, storageKey, ...args);
        },
      });
    }, { key: launcherPositionKey, mode: scenario });
    await page.goto('/home', { waitUntil: 'domcontentloaded' });
    const launcher = page.getByRole('button', { name: '챗봇', exact: true });
    if (scenario !== 'write-denied') {
      expect(await launcher.evaluate(element => ({ left: element.style.left, top: element.style.top })))
        .toEqual({ left: '', top: '' });
    }
    await dragLauncher(page, launcher, { x: 160, y: 280 });
    await page.mouse.move(8, 8);
    const dropped = (await launcher.boundingBox())!;
    expect(dropped.x).toBeGreaterThan(100);
    expect(dropped.x).toBeLessThan(160);
    await expect(page).toHaveURL(/\/home$/);
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
}
