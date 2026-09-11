import { expect, test } from 'playwright/test';

test.setTimeout(120_000);
test.beforeEach(async ({ page }) => {
  await page.route(url => url.pathname.startsWith('/api/'), route => route.abort());
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
  // Ordinary challenge routes use the official API; keep this synthetic session authenticated.
  for (const resource of ['challenges', 'badges']) {
    await page.route(`**/api/v1/user/${resource}`, route => route.fulfill({ json: { items: [], total_count: 0 } }));
  }
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'back-navigation-test');
    sessionStorage.setItem('poke.account-principal', 'back@example.com');
  });
});

test('challenge My returns to the home it was opened from', async ({ page }) => {
  await page.goto('/dev/home-challenges');
  await page.getByRole('link', { name: '전체 보기', exact: true }).click();
  await expect(page).toHaveURL('/dev/challenges');
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/dev/home-challenges');
});

test('direct challenge entry has a full-width shared header, safe home fallback, and accessible touch target', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/challenges');
  const header = page.locator('header').filter({ has: page.getByRole('button', { name: '뒤로 가기', exact: true }) });
  await expect(header).toBeVisible();
  await expect(header).toHaveCSS('height', '64px');
  await expect(header).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(header).toHaveCSS('border-bottom-style', 'solid');
  const headerBounds = await header.boundingBox();
  const scrollportWidth = await header.evaluate((element) => element.parentElement!.clientWidth);
  const tabsBounds = await page.getByRole('navigation', { name: '챌린지 보기' }).boundingBox();
  expect(headerBounds).not.toBeNull();
  expect(tabsBounds).not.toBeNull();
  expect(headerBounds!.x).toBe(0);
  expect(headerBounds!.width).toBe(scrollportWidth);
  expect(tabsBounds!.x - headerBounds!.x).toBe(20);
  const back = page.getByRole('button', { name: '뒤로 가기', exact: true });
  await expect(back).toBeVisible();
  await expect(back.locator('svg')).toHaveAttribute('aria-hidden', 'true');
  const bounds = await back.boundingBox();
  expect(bounds!.width).toBeGreaterThanOrEqual(44);
  expect(bounds!.height).toBeGreaterThanOrEqual(44);
  await header.screenshot({ path: testInfo.outputPath('challenge-shared-header.png') });
  await back.click();
  await expect(page).toHaveURL('/home');
});

test('browse tab also exposes back navigation', async ({ page }) => {
  await page.goto('/dev/challenges');
  await page.getByRole('link', { name: '둘러보기', exact: true }).click();
  await expect(page).toHaveURL('/dev/challenges/browse');
  const header = page.getByRole('banner');
  await expect(header).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/dev/challenges');
});
