import { expect, test } from 'playwright/test';

test.setTimeout(120_000);
test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
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

test('direct challenge entry has a safe home fallback and accessible touch target', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/challenges');
  const back = page.getByRole('button', { name: '뒤로 가기', exact: true });
  await expect(back).toBeVisible();
  const bounds = await back.boundingBox();
  expect(bounds!.width).toBeGreaterThanOrEqual(44);
  expect(bounds!.height).toBeGreaterThanOrEqual(44);
  await back.click();
  await expect(page).toHaveURL('/home');
});

test('browse tab also exposes back navigation', async ({ page }) => {
  await page.goto('/dev/challenges');
  await page.getByRole('link', { name: '둘러보기', exact: true }).click();
  await page.getByRole('button', { name: '뒤로 가기', exact: true }).click();
  await expect(page).toHaveURL('/dev/challenges');
});
