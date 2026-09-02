import { expect, test } from 'playwright/test';

import { IS_REAL_API } from './helpers/mode';

test.beforeEach(() => {
  test.skip(!IS_REAL_API, '401 세션 만료 처리는 실 API 클라이언트 모드에서 검증합니다.');
});

test('보호 API가 401을 반환하면 세션을 지우고 로그인 화면으로 보낸다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'opaque-server-token');
    sessionStorage.setItem('poke.account-principal', 'server-expired@example.com');
  });
  await page.route('**/api/v1/users/me', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'INVALID_TOKEN', message: '인증이 만료되었습니다.' }),
    });
  });

  await page.goto('/my/profile');

  await expect(page).toHaveURL(/\/login$/);
  await expect
    .poll(() =>
      page.evaluate(() => ({
        token: sessionStorage.getItem('poke.access-token'),
        principal: sessionStorage.getItem('poke.account-principal'),
      })),
    )
    .toEqual({ token: null, principal: null });
});
