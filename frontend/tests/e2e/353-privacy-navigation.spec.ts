import { expect, test, type Page } from 'playwright/test';

async function openSignupProfileStep(page: Page) {
  await page.route('**/api/v1/auth/email-verifications', async (route) => {
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ verification_id: 353, expires_in: 180, resend_available_in: 60 }),
    });
  });
  await page.route('**/api/v1/auth/email-verifications/353/verify', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ verification_token: 'privacy-verification-token', expires_in: 600 }),
    });
  });

  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  await page.getByLabel('이메일').fill('privacy-navigation@example.com');
  await page.getByRole('button', { name: '인증코드 받기' }).click();
  await page.getByLabel('인증코드').fill('123456');
  await page.getByRole('button', { name: '확인' }).click();
  await page.getByLabel('비밀번호', { exact: true }).fill('ValidPass123!');
  await page.getByLabel('비밀번호 확인', { exact: true }).fill('ValidPass123!');
  await page.getByRole('button', { name: '다음' }).click();
  await page.getByLabel('이름').fill('개인정보사용자');
  await page.getByLabel('전화번호').fill('010-1234-5678');
  await page.getByLabel('생년월일').fill('1991-02-03');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /개인정보 수집 및 이용에 동의해요/ }).check();
}

test('회원가입 개인정보 처리 안내는 같은 화면에서 열리고 뒤로 가면 폼이 보존된다', async ({
  page,
  context,
}) => {
  await openSignupProfileStep(page);

  const initialPageCount = context.pages().length;
  await page.getByText('개인정보 처리 안내 보기', { exact: true }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: '개인정보 처리 안내' })).toBeVisible();
  expect(context.pages()).toHaveLength(initialPageCount);

  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page.getByText('4 / 4 단계', { exact: true })).toBeVisible();
  await expect(page.getByLabel('이름')).toHaveValue('개인정보사용자');
  await expect(page.getByLabel('전화번호')).toHaveValue('010-1234-5678');
  await expect(page.getByLabel('생년월일')).toHaveValue('1991-02-03');
  await expect(page.getByRole('radio', { name: '여성' })).toBeChecked();
  await expect(
    page.getByRole('checkbox', { name: /개인정보 수집 및 이용에 동의해요/ }),
  ).toBeChecked();

  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page.getByLabel('비밀번호', { exact: true })).toHaveValue('ValidPass123!');
  await expect(page.getByLabel('비밀번호 확인', { exact: true })).toHaveValue('ValidPass123!');

  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await expect(page.getByLabel('인증코드')).toHaveValue('123456');

  const storageDump = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(storageDump).not.toContain('ValidPass123!');
  expect(storageDump).not.toContain('123456');
});
