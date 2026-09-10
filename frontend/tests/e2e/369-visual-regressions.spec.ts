import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.use({ viewport: { width: 390, height: 844 } });
test.beforeEach(() => test.skip(IS_REAL_API, MOCK_ONLY_REASON));

test('MY switch keeps the 32px pill visible without painting the 44px hitbox', async ({ page }, testInfo) => {
  await page.goto('/dev/my-authenticated');
  const control = page.getByRole('switch', { name: '복약 알림' });
  await expect(control).toBeVisible();
  const appearance = await control.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    trackBackground: getComputedStyle(element, '::before').backgroundColor,
    trackHeight: getComputedStyle(element, '::before').height,
  }));
  expect(appearance.background).toBe('rgba(0, 0, 0, 0)');
  expect(appearance.trackBackground).not.toBe('rgba(0, 0, 0, 0)');
  expect(appearance.trackHeight).toBe('32px');
  expect((await control.boundingBox())?.height).toBe(44);
  await page.screenshot({ path: testInfo.outputPath('my-switch-390x844.png') });
});

test('badge capture waits for decoded original artwork', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await page.goto('/dev/challenges/badges');
  const images = page.getByRole('img');
  await expect(images.first()).toBeVisible();
  await images.evaluateAll(async (elements) => {
    await Promise.all(elements.map(element => (element as HTMLImageElement).decode()));
  });
  expect(await images.evaluateAll(elements => elements.every(element => {
    const image = element as HTMLImageElement;
    return image.complete && image.naturalWidth > 0 && image.naturalHeight > 0;
  }))).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('badges-decoded-390x844.png') });
});
