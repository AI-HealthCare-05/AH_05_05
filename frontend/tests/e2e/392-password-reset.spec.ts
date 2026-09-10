import { expect, test } from 'playwright/test';

test.setTimeout(60_000);
test.beforeEach(async ({ page }) => {
  await page.route(/fonts\.(googleapis|gstatic)\.com/, route => route.abort());
  // No unmatched request may reach a real account/email service.
  await page.route(url => url.pathname.startsWith('/api/'), route => route.abort());
});

test('reset opens over login and closes without navigation or sending', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/auth/password-reset', async route => {
    requests += 1;
    await route.fulfill({ status: 202, json: { detail: '요청을 처리했습니다.' } });
  });
  await page.goto('/login');
  await page.getByRole('button', { name: '재설정', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('dialog', { name: '비밀번호 재설정' })).toBeVisible();
  await expect(page.getByLabel('이메일 주소')).toHaveValue('');
  await page.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '재설정', exact: true })).toBeFocused();
  await expect(page).toHaveURL(/\/login$/);
  expect(requests).toBe(0);
});

test('separate email can be edited, validated and sent once while pending', async ({ page }) => {
  const payloads: unknown[] = [];
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/auth/password-reset', async route => {
    payloads.push(route.request().postDataJSON());
    await held;
    await route.fulfill({ status: 202, json: { detail: '요청을 처리했습니다.' } });
  });
  await page.goto('/login');
  await page.getByLabel('이메일', { exact: true }).fill('first@example.com');
  await page.getByRole('button', { name: '재설정', exact: true }).click();
  const email = page.getByLabel('이메일 주소');
  await expect(email).toHaveValue('first@example.com');
  await email.fill('invalid');
  await page.getByRole('button', { name: '임시비밀번호 발송' }).click();
  expect(await email.evaluate((input: HTMLInputElement) => input.validity.valid)).toBe(false);
  expect(payloads).toEqual([]);
  await email.fill('second@example.com');
  await page.getByRole('button', { name: '임시비밀번호 발송' }).click();
  await expect(page.getByRole('button', { name: '발송 요청 중...' })).toBeDisabled();
  await expect(email).toBeDisabled();
  await page.getByRole('dialog').locator('form').dispatchEvent('submit');
  await page.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect.poll(() => payloads.length).toBe(1);
  release();
  await expect(page.getByRole('status')).toContainText('발송을 요청했어요');
  expect(payloads).toEqual([{ email: 'second@example.com' }]);
  await expect(page.getByRole('button', { name: '임시비밀번호 발송' })).toHaveCount(0);
  await page.getByRole('button', { name: '로그인으로 돌아가기' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel('이메일', { exact: true })).toHaveValue('first@example.com');
});

test('failed request retains email for retry; direct entry back has a login fallback', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/auth/password-reset', async route => {
    requests += 1;
    await route.fulfill(requests === 1
      ? { status: 503, json: { message: 'unavailable' } }
      : { status: 202, json: { detail: '요청을 처리했습니다.' } });
  });
  await page.goto('/password-reset');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('dialog', { name: '비밀번호 재설정' })).toBeVisible();
  await page.getByLabel('이메일 주소').fill('retry@example.com');
  await page.getByRole('button', { name: '임시비밀번호 발송' }).click();
  await expect(page.getByRole('alert')).toContainText('다시 시도');
  await expect(page.getByLabel('이메일 주소')).toHaveValue('retry@example.com');
  await page.getByRole('button', { name: '임시비밀번호 발송' }).click();
  await expect(page.getByRole('status')).toBeVisible();
  expect(requests).toBe(2);
  await page.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.reload();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

for (const width of [320, 390, 1280]) {
  test(`reset fields and actions fit ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/login');
    const tabsBefore = await page.getByRole('group', { name: '인증 방식' }).boundingBox();
    await page.getByRole('button', { name: '재설정', exact: true }).click();
    await expect(page.getByLabel('이메일 주소')).toBeVisible();
    await expect(page.getByRole('button', { name: '임시비밀번호 발송' })).toBeInViewport();
    const sheet = page.getByRole('dialog', { name: '비밀번호 재설정' });
    await sheet.evaluate(async element => {
      await Promise.all(element.getAnimations().map(animation => animation.finished));
    });
    const sheetBox = await sheet.boundingBox();
    expect(sheetBox!.width).toBeLessThanOrEqual(Math.min(width, 390));
    expect(sheetBox!.x).toBeCloseTo((width - sheetBox!.width) / 2, 0);
    expect(sheetBox!.y + sheetBox!.height).toBeCloseTo(844, 0);
    expect(sheetBox!.height).toBeLessThan(500);
    const tabsAfter = await page.locator('[aria-label="인증 방식"]').boundingBox();
    expect(tabsAfter).toEqual(tabsBefore);
    await expect(sheet.getByRole('group', { name: '인증 방식' })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    const box = await page.getByLabel('이메일 주소').boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    await page.screenshot({ path: testInfo.outputPath(`password-reset-${width}.png`), fullPage: true });
  });
}
