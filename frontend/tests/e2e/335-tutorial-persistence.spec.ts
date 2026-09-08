import { expect, test } from 'playwright/test';

test.setTimeout(120_000);
test.beforeEach(async ({ context }) => {
  await context.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
});

for (const exit of ['건너뛰기', '둘러보기', '시작하기']) {
  test(`${exit} 이후 새 브라우저 세션에서 튜토리얼을 다시 표시하지 않는다`, async ({ page, context, browser }) => {
    await page.goto('/tutorial');
    if (exit === '시작하기') {
      for (let step = 0; step < 3; step++) await page.getByRole('button', { name: '다음', exact: true }).click();
    }
    await page.getByRole('button', { name: exit, exact: true }).click();
    await expect(page).toHaveURL(/\/home$/);

    // Restore durable browser data only; Playwright storageState excludes sessionStorage.
    const nextSession = await browser.newContext({ storageState: await context.storageState() });
    try {
      await nextSession.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
      const nextPage = await nextSession.newPage();
      await nextPage.goto(new URL('/', page.url()).href);
      await expect(nextPage).toHaveURL(/\/home$/);
      await nextPage.goto(new URL('/tutorial', page.url()).href);
      await expect(nextPage).toHaveURL(/\/home$/);
    } finally {
      await nextSession.close();
    }
  });
}

test('아직 완료하거나 건너뛰지 않았다면 새 탭에서도 튜토리얼을 표시한다', async ({ page, context }) => {
  await page.goto('/tutorial');
  await page.getByRole('button', { name: '다음', exact: true }).click();
  const nextPage = await context.newPage();
  await nextPage.goto(new URL('/', page.url()).href);
  await expect(nextPage).toHaveURL(/\/tutorial$/);
  await expect(nextPage.getByRole('button', { name: '건너뛰기' })).toBeVisible();
});

test('브라우저 영구 저장에 실패해도 튜토리얼을 종료할 수 있다', async ({ page }) => {
  await page.addInitScript(() => {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (this === window.localStorage) throw new DOMException('Full', 'QuotaExceededError');
      return setItem.call(this, key, value);
    };
  });
  await page.goto('/tutorial');
  await page.getByRole('button', { name: '건너뛰기' }).click();
  await expect(page).toHaveURL(/\/home$/);
  await page.goto('/');
  await expect(page).toHaveURL(/\/home$/);
});
