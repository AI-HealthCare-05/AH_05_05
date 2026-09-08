import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(20_000);

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('이메일').fill('patient@example.com');
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await expect(page).toHaveURL(/\/home$/);
}

test('게스트가 하단 마이를 누르면 홈에 머물며 기존 로그인 안내 시트를 연다', async ({ page }) => {
  await page.goto('/home');

  await page.getByRole('button', { name: '마이', exact: true }).click();

  const prompt = page.getByRole('dialog');
  await expect(prompt).toBeVisible();
  await expect(
    prompt.getByRole('heading', { name: '로그인하고, 나만의 복약관리를 시작해 보세요.' }),
  ).toBeVisible();
  await expect(prompt.getByRole('button', { name: '로그인 · 회원가입' })).toBeVisible();
  await expect(page).toHaveURL(/\/home$/);
});

test('로그인한 사용자가 하단 마이를 누르면 마이 화면으로 이동한다', async ({ page }) => {
  await logIn(page);

  await page.getByRole('button', { name: '마이', exact: true }).click();

  await expect(page).toHaveURL(/\/my$/);
});
