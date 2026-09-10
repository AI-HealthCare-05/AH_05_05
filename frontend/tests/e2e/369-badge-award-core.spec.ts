import { readFileSync } from 'node:fs';
import { expect, test, type Page } from 'playwright/test';

test.skip(process.env.VITE_USE_MOCK !== 'false', 'Uses isolated award and image fixtures.');
test.setTimeout(60_000);
const artwork = readFileSync(process.env.BADGE_ART_FIXTURE_PATH ?? new URL('../../../app/static/media/badges/water-badge.png', import.meta.url));
const sample = { source: 'official', awardId: 901, participationId: 501, name: '꾸준한 실천 배지', imageUrl: '/media/server-award.png' };

async function openApp(page: Page, failImage = false) {
  let failed = failImage;
  let artReads = 0;
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('poke.access-token')) {
      sessionStorage.setItem('poke.access-token', 'badge-test');
      sessionStorage.setItem('poke.account-principal', 'badge-a@example.com');
    }
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/media/server-award.png', route => {
    artReads += 1;
    return failed ? route.fulfill({ status: 503, body: '' }) : route.fulfill({ contentType: 'image/png', body: artwork });
  });
  await page.goto('/privacy');
  await expect(page.locator('main')).toBeVisible();
  return { artReads: () => artReads, recover: () => { failed = false; } };
}

async function enqueue(page: Page, overrides: Record<string, unknown> = {}) {
  return page.evaluate(async award => {
    const path = '/src/shared/lib/badgeAwards.ts';
    const store = await import(/* @vite-ignore */ path);
    return store.enqueueBadgeAward(store.captureBadgeAwardScope(sessionStorage.getItem('poke.account-principal')), award);
  }, { ...sample, ...overrides });
}

test('StrictMode queue dedupes rerenders, duplicate callbacks and reloads but keeps different participations', async ({ page }) => {
  await openApp(page);
  expect(await enqueue(page)).toBe(true);
  expect(await enqueue(page)).toBe(false);
  const dialog = page.getByRole('dialog', { name: '배지를 획득했어요!' });
  await expect(dialog).toHaveCount(1);
  await expect(dialog).toHaveAttribute('data-phase', 'ready');
  await dialog.getByRole('button', { name: '확인', exact: true }).click();
  await page.goto('/terms');
  expect(await enqueue(page)).toBe(false);
  await page.reload();
  expect(await enqueue(page)).toBe(false);
  expect(await enqueue(page, { participationId: 502 })).toBe(true);
  await expect(dialog).toHaveCount(1);
});

test('baseline observations remain silent and enqueue requires the current captured account generation', async ({ page }) => {
  await openApp(page);
  const scope = await page.evaluate(async award => {
    const path = '/src/shared/lib/badgeAwards.ts';
    const store = await import(/* @vite-ignore */ path);
    const captured = store.captureBadgeAwardScope('badge-a@example.com');
    store.observeBadgeAwards(captured, [award]);
    return captured;
  }, sample);
  expect(await enqueue(page)).toBe(false);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.evaluate(async () => {
    const path = '/src/shared/api/client.ts';
    const client = await import(/* @vite-ignore */ path);
    client.setAccessToken('replacement-token');
  });
  const stale = await page.evaluate(async ({ captured, award }) => {
    const path = '/src/shared/lib/badgeAwards.ts';
    const store = await import(/* @vite-ignore */ path);
    return store.enqueueBadgeAward(captured, award);
  }, { captured: scope, award: { ...sample, awardId: 902 } });
  expect(stale).toBe(false);
  await page.evaluate(() => {
    sessionStorage.setItem('poke.access-token', 'badge-b-token');
    sessionStorage.setItem('poke.account-principal', 'badge-b@example.com');
  });
  await page.reload();
  expect(await enqueue(page)).toBe(true);
  await expect(page.getByRole('dialog')).toHaveCount(1);
});

test('edge flood fill removes outer white and preserves enclosed white and diagonal-only islands exactly', async ({ page }) => {
  await openApp(page);
  const result = await page.evaluate(async () => {
    const path = '/src/shared/lib/badgeArt.ts';
    const { removeOuterWhite } = await import(/* @vite-ignore */ path);
    const frame = new ImageData(5, 5);
    for (let i = 0; i < 25; i += 1) frame.data.set([255, 255, 255, 255], i * 4);
    for (let y = 1; y <= 3; y += 1) for (let x = 1; x <= 3; x += 1) frame.data.set([5, 95, 90, 255], (y * 5 + x) * 4);
    frame.data.set([255, 255, 255, 255], 12 * 4);
    frame.data.set([255, 255, 255, 255], 6 * 4); // Reaches the outside but only diagonally touches the center.
    removeOuterWhite(frame);
    return { corner: [...frame.data.slice(0, 4)], center: [...frame.data.slice(48, 52)], ring: [...frame.data.slice(28, 32)] };
  });
  expect(result).toEqual({ corner: [255, 255, 255, 0], center: [255, 255, 255, 255], ring: [5, 95, 90, 255] });
});

test('a confirmed transition can promote silent observation but cannot replay a presented award', async ({ page }) => {
  await openApp(page);
  const result = await page.evaluate(async award => {
    const path = '/src/shared/lib/badgeAwards.ts';
    const store = await import(/* @vite-ignore */ path);
    const scope = store.captureBadgeAwardScope('badge-a@example.com');
    store.observeBadgeAwards(scope, [award]);
    const ordinary = store.enqueueBadgeAward(scope, award);
    const transition = store.enqueueBadgeAward(scope, award, { confirmedTransition: true });
    const duplicate = store.enqueueBadgeAward(scope, award, { confirmedTransition: true });
    return { ordinary, transition, duplicate };
  }, sample);
  expect(result).toEqual({ ordinary: false, transition: true, duplicate: false });
  await expect(page.getByRole('dialog')).toHaveCount(1);
});

test('queued awards wait for an existing dialog without closing it', async ({ page }) => {
  await openApp(page);
  await page.evaluate(() => {
    const existing = document.createElement('dialog');
    existing.id = 'existing-dialog';
    existing.setAttribute('aria-label', '진행 중인 작업');
    existing.textContent = '진행 중인 작업을 먼저 마쳐요.';
    document.body.append(existing);
    existing.showModal();
  });
  await enqueue(page);
  await expect(page.getByRole('dialog', { name: '진행 중인 작업' })).toBeVisible();
  await expect(page.getByRole('dialog', { name: '배지를 획득했어요!' })).toHaveCount(0);
  await page.evaluate(() => document.getElementById('existing-dialog')?.remove());
  await expect(page.getByRole('dialog', { name: '배지를 획득했어요!' })).toBeVisible();
});

test('decoded image is bounded and cached once per URL, with released presentation URLs', async ({ page }) => {
  const fixture = await openApp(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await enqueue(page);
  const dialog = page.getByRole('dialog');
  const image = dialog.getByRole('img');
  await expect(image).toBeVisible();
  const details = await image.evaluate((element: HTMLImageElement) => ({ width: element.naturalWidth, height: element.naturalHeight, ready: element.complete, src: element.src }));
  expect(Math.max(details.width, details.height)).toBeLessThanOrEqual(512);
  expect(details.ready).toBe(true);
  await dialog.getByRole('button', { name: '확인', exact: true }).click();
  await expect.poll(() => page.evaluate(async url => { try { await fetch(url); return false; } catch { return true; } }, details.src)).toBe(true);
  await enqueue(page, { awardId: 902, participationId: 502 });
  await expect(dialog.getByRole('img')).toBeVisible();
  expect(fixture.artReads()).toBe(1);
});

test('image failure shows no opaque artwork and allows retry and confirmation', async ({ page }) => {
  const fixture = await openApp(page, true);
  await enqueue(page);
  const dialog = page.getByRole('dialog');
  await expect(dialog).toHaveAttribute('data-phase', 'error');
  await expect(dialog.getByRole('img')).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: '확인', exact: true })).toBeEnabled();
  fixture.recover();
  await dialog.getByRole('button', { name: '이미지 다시 불러오기' }).click();
  await expect(dialog.getByRole('img')).toBeVisible();
  await expect(dialog).toHaveAttribute('data-phase', 'ready');
  await dialog.getByRole('button', { name: '확인', exact: true }).click();
  expect(fixture.artReads()).toBe(2);
});

test('CORS rejection stays explicit and Escape closes a loading or failed award', async ({ page }) => {
  await openApp(page);
  await page.route('https://badge.invalid/art.png', route => route.abort('accessdenied'));
  await enqueue(page, { imageUrl: 'https://badge.invalid/art.png' });
  const dialog = page.getByRole('dialog');
  await expect(dialog).toHaveAttribute('data-phase', 'error');
  await expect(dialog.getByRole('alert')).toBeVisible();
  await expect(dialog.getByRole('img')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
});

test('reduced motion shows confirmation immediately without 3D or gloss and keeps keyboard focus', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openApp(page);
  await enqueue(page);
  const dialog = page.getByRole('dialog');
  const confirm = dialog.getByRole('button', { name: '확인', exact: true });
  await expect(confirm).toBeVisible();
  await expect(dialog.locator('.badge-award-mask')).toHaveCount(0);
  expect(await dialog.locator('.badge-award-stage').evaluate(element => getComputedStyle(element).perspective)).toBe('none');
  await page.keyboard.press('Tab');
  await expect(confirm).toBeFocused();
  expect((await confirm.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await confirm.press('Enter');
  await expect(dialog).toHaveCount(0);
});

for (const initiallyReduced of [false, true]) {
  test(`motion preference changes never replay a settled award (initial reduced: ${initiallyReduced})`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: initiallyReduced ? 'reduce' : 'no-preference' });
    await openApp(page);
    await enqueue(page);
    const dialog = page.getByRole('dialog');
    await expect(dialog).toHaveAttribute('data-phase', 'ready');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(dialog.locator('.badge-award-mask')).toHaveCount(0);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect(dialog.locator('.badge-award-mask')).toHaveCount(1);
    expect(await dialog.getAttribute('data-phase')).toBe('ready');
    expect(await dialog.locator('.badge-award-art').evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === 'running').length)).toBe(0);
    await expect(dialog.getByRole('button', { name: '확인', exact: true })).toBeVisible();
  });
}

for (const width of [320, 390]) {
  test(`normal ${width}px presentation settles, shines once, then reveals copy and confirmation`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await openApp(page);
    await enqueue(page);
    const dialog = page.getByRole('dialog');
    await expect(dialog).toHaveAttribute('data-phase', 'tilt');
    await expect(dialog.getByRole('button', { name: '확인', exact: true })).toHaveCount(0);
    await dialog.locator('.badge-award-art').evaluate(element => { const entry = element.getAnimations()[0]; entry.pause(); entry.currentTime = 450; });
    await page.screenshot({ path: testInfo.outputPath(`badge-${width}-tilt.png`) });
    await dialog.locator('.badge-award-art').evaluate(element => element.getAnimations()[0].finish());
    await page.waitForFunction(() => document.querySelector('[data-badge-award-dialog]')?.getAttribute('data-phase') === 'gloss');
    await dialog.locator('.badge-award-gloss').evaluate(element => { const sweep = element.getAnimations()[0]; sweep.pause(); sweep.currentTime = 225; });
    await page.screenshot({ path: testInfo.outputPath(`badge-${width}-gloss.png`) });
    await dialog.locator('.badge-award-gloss').evaluate(element => element.getAnimations()[0].finish());
    await expect(dialog).toHaveAttribute('data-phase', 'ready');
    await expect(dialog.getByRole('button', { name: '확인', exact: true })).toBeVisible();
    const effects = await dialog.locator('.badge-award-art').evaluate(element => element.getAnimations({ subtree: true }).map(animation => ({ iterations: animation.effect?.getTiming().iterations, state: animation.playState })));
    expect(effects.every(effect => effect.iterations === 1 && effect.state === 'finished')).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`badge-${width}-ready.png`) });
  });
}
