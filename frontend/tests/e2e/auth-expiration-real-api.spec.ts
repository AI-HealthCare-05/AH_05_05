import { expect, test } from 'playwright/test';

import { IS_REAL_API } from './helpers/mode';

test.beforeEach(() => {
  test.skip(!IS_REAL_API, '401 세션 만료 처리는 실 API 클라이언트 모드에서 검증합니다.');
});

test('보호 API와 토큰 갱신이 모두 401이면 세션을 지우고 로그인 화면으로 보낸다', async ({ page }) => {
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
  await page.route('**/api/v1/auth/token/refresh', route => route.fulfill({ status: 401, json: {} }));

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

test('보호 API의 401은 갱신 후 한 번 재시도하고 세션을 유지한다', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'old-token');
    sessionStorage.setItem('poke.account-principal', 'active@example.com');
  });
  await page.route(/\/api\/v1\//, route => route.fulfill({ json: {} }));
  let refreshes = 0;
  await page.route('**/api/v1/auth/token/refresh', route => {
    refreshes++;
    return route.fulfill({ json: { access_token: 'new-token' } });
  });
  let attempts = 0;
  await page.route('**/api/v1/session-probe', route => {
    attempts++;
    return route.request().headers().authorization === 'Bearer new-token'
      ? route.fulfill({ json: { ok: true } })
      : route.fulfill({ status: 401, json: {} });
  });
  await page.goto('/ocr-review?batchId=probe');
  const result = await page.evaluate(async () => {
    const { http } = await import('/src/shared/api/client.ts');
    return http.get('/v1/session-probe').catch(() => ({ ok: false }));
  });
  expect(result).toEqual({ ok: true });
  expect(refreshes).toBe(1);
  expect(attempts).toBe(2);
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('poke.access-token'))).toBe('new-token');
});
