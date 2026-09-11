import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(45_000);

test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route('**/api/v1/**', route => route.fulfill({ status: 404, json: {} }));
});

for (const width of [320, 390, 1488]) {
  test(`chat launcher remains recognizable and clear of navigation (${width})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/home', { waitUntil: 'domcontentloaded' });
    const launcher = page.getByRole('button', { name: '챗봇', exact: true });
    await expect(launcher).toBeInViewport({ ratio: 1 });
    const picture = launcher.locator('img');
    await expect.poll(() => picture.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
    // The source has wide blank margins: its rendered chick must occupy more than
    // the old 25px-wide avatar, while its frame stays inside the touch target.
    const pictureBox = (await picture.boundingBox())!;
    expect(pictureBox.width * (208 / 462)).toBeGreaterThanOrEqual(34);
    await expect(launcher.locator('[data-chat-indicator]')).toBeVisible();
    const box = (await launcher.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(56);
    expect(box.width).toBeLessThanOrEqual(60);
    const navBox = (await page.getByRole('navigation', { name: '주요 화면' }).boundingBox())!;
    expect(box.y + box.height).toBeLessThanOrEqual(navBox.y - 8);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(launcher).toHaveCSS('animation-name', 'none');
    await launcher.focus();
    await expect(launcher).toBeFocused();
    const outline = await launcher.evaluate(element => getComputedStyle(element).outlineWidth);
    expect(parseFloat(outline)).toBeGreaterThanOrEqual(2);
    await launcher.evaluate(element => (element as HTMLButtonElement).blur());
    await page.screenshot({ path: testInfo.outputPath(`chat-launcher-${width}.png`) });
    await launcher.screenshot({ path: testInfo.outputPath(`chat-launcher-detail-${width}.png`) });
  });
}

test('guest keyboard activation opens login prompt and hides the launcher until dismissed', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/home', { waitUntil: 'domcontentloaded' });
  const launcher = page.getByRole('button', { name: '챗봇', exact: true });
  await expect(launcher).toHaveCSS('transition-duration', '0s');
  await launcher.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(launcher).toBeHidden();
  await dialog.getByRole('button', { name: '다음에 할게요' }).click();
  await expect(launcher).toBeVisible();
  await expect(page).toHaveURL(/\/home$/);
});
