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

test('정지 계정도 자격증명 오류와 구분되지 않는 응답을 받는다', async ({ page }) => {
  // 사유를 알려주면 그 이메일이 가입돼 있다는 사실이 새어나간다(#196).
  // 문구뿐 아니라 상태 코드까지 같아야 한다 — 예전에는 423 으로 갈라져 있었다.
  const response = page.waitForResponse((r) => r.url().includes('/auth/login'));
  await submitLogin(page, SUSPENDED.email, SUSPENDED.password);

  expect((await response).status()).toBe(400);
  await expect(page.getByText('이메일 또는 비밀번호가 올바르지 않습니다.')).toBeVisible();
  await expect(page.getByText('비활성화된 계정입니다.')).toHaveCount(0);
  await expect(page).toHaveURL(/\/login$/);
});

/**
 * 유저플로우 v4 의 "토큰을 저장하지 않는다"를 검증하는 테스트입니다.
 *
 * 지금은 건너뜁니다. 이 PR 은 로그인 연동만 담고, 토큰 보관 위치는 팀 미확정 사안이라
 * shared/api/client.ts 를 main 것으로 되돌렸습니다(= sessionStorage 저장 유지).
 * OCR 작업이 restoreAccessToken() 에 의존해 단독으로 바꿀 수 없습니다.
 *
 * 정책이 정해지면 되살립니다. 지우지 마세요 — v4 요구사항의 유일한 실행 가능한 기록입니다.
 */
test.skip('토큰은 메모리에만 있어 새로고침하면 로그아웃된다', async ({ page }) => {
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
