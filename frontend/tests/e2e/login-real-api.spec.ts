/**
 * 실제 백엔드에 붙은 로그인 화면 검증.
 *
 * 다른 e2e 는 목업으로 돌지만 이 파일만 실서버가 필요합니다. 실행 전에:
 *   1. 백엔드를 띄운다 (uv run uvicorn app.main:app --port 8013)
 *   2. frontend/.env.local 에 VITE_USE_MOCK=false, VITE_API_PROXY_TARGET 을 넣는다
 *   3. 아래 계정 두 개가 DB 에 있어야 한다 (ACTIVE / SUSPENDED)
 *
 * 그래서 기본 실행에서는 건너뜁니다. 돌리려면 E2E_REAL_API=1 을 켜세요.
 */
import { expect, test } from 'playwright/test';

const ACTIVE = { email: 'login89@example.com', password: 'Passw0rd!23' };
const SUSPENDED = { email: 'locked89@example.com', password: 'Passw0rd!23' };

test.skip(process.env.E2E_REAL_API !== '1', '실서버와 시드 계정이 필요합니다.');

async function submitLogin(page: import('playwright/test').Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('이메일').fill(email);
  await page.getByLabel('비밀번호').fill(password);
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
}

test('정상 계정은 /api/v1/auth/login 을 그대로 호출하고 홈으로 넘어간다', async ({ page }) => {
  const request = page.waitForRequest((r) => r.url().includes('/auth/login'));
  await submitLogin(page, ACTIVE.email, ACTIVE.password);

  // 프록시가 접두사를 떼지 않는지 확인합니다. rewrite 가 살아 있으면 /v1/... 로 나갑니다.
  expect(new URL((await request).url()).pathname).toBe('/api/v1/auth/login');
  await expect(page).toHaveURL(/\/home$/);
});

test('비밀번호가 틀리면 서버 문구를 그대로 띄우고 화면에 남는다', async ({ page }) => {
  await submitLogin(page, ACTIVE.email, 'WrongPass!99');

  await expect(page.getByText('이메일 또는 비밀번호가 올바르지 않습니다.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('없는 이메일도 비밀번호 오류와 같은 문구를 낸다', async ({ page }) => {
  // 가입 여부가 새어나가면 안 되므로 두 경우의 문구가 같아야 합니다.
  await submitLogin(page, 'no-such-user-89@example.com', ACTIVE.password);

  await expect(page.getByText('이메일 또는 비밀번호가 올바르지 않습니다.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('정지 계정은 423 을 받아 비활성 문구를 띄운다', async ({ page }) => {
  const response = page.waitForResponse((r) => r.url().includes('/auth/login'));
  await submitLogin(page, SUSPENDED.email, SUSPENDED.password);

  expect((await response).status()).toBe(423);
  await expect(page.getByText('비활성화된 계정입니다.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('토큰은 메모리에만 있어 새로고침하면 로그아웃된다', async ({ page }) => {
  await submitLogin(page, ACTIVE.email, ACTIVE.password);
  await expect(page).toHaveURL(/\/home$/);

  const stored = await page.evaluate(() => ({
    local: JSON.stringify(window.localStorage),
    session: JSON.stringify(window.sessionStorage),
  }));
  expect(stored.local).not.toContain('eyJ');
  expect(stored.session).not.toContain('eyJ');

  await page.reload();
  await expect(page.getByRole('region', { name: '포케 기능 소개' })).toBeVisible();
});
