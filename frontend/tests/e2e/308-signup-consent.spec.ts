import { expect, test, type Page } from 'playwright/test';

// WSL이 Windows 파일시스템의 Vite 모듈을 처음 읽을 때 첫 탐색이 20초를 넘길 수 있습니다.
test.setTimeout(45_000);

const REQUIRED_CONSENTS = [
  /서비스 이용약관에 동의해요/,
  /개인정보 수집 및 이용에 동의해요/,
  /만 14세 이상이에요/,
  /진료기록 수집 및 이용에 동의해요/,
  /AI 서비스 이용에 동의해요/,
] as const;

async function mockSignupRoutes(page: Page) {
  await page.route('**/api/v1/auth/email-verifications', async (route) => {
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ verification_id: 308, expires_in: 180, resend_available_in: 60 }),
    });
  });
  await page.route('**/api/v1/auth/email-verifications/308/verify', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ verification_token: 'consent-verification-token', expires_in: 600 }),
    });
  });
}

async function openProfileStep(page: Page, birthDate = '1990-01-01') {
  await mockSignupRoutes(page);
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
  await page.getByLabel('이메일').fill('consent@example.com');
  await page.getByRole('button', { name: '인증코드 받기' }).click();
  await page.getByLabel('인증코드').fill('123456');
  await page.getByRole('button', { name: '확인' }).click();
  await page.getByLabel('비밀번호', { exact: true }).fill('Password123!');
  await page.getByLabel('비밀번호 확인', { exact: true }).fill('Password123!');
  await page.getByRole('button', { name: '다음' }).click();
  await page.getByLabel('이름').fill('동의확인');
  await page.getByLabel('전화번호').fill('010-1234-5678');
  await page.getByLabel('생년월일').fill(birthDate);
  await page.getByRole('radio', { name: '여성' }).check();
}

async function checkAllRequiredConsents(page: Page) {
  for (const name of REQUIRED_CONSENTS) {
    await page.getByRole('checkbox', { name }).check();
  }
}

test('필수 동의는 약관 링크와 실제 수집·이용 내용을 보여주고 각각 가입을 제한한다', async ({
  page,
}) => {
  await openProfileStep(page);

  const termsLink = page.getByRole('link', { name: '서비스 이용약관 보기' });
  await expect(termsLink).toHaveAttribute('href', '/terms');
  await expect(termsLink).toHaveAttribute('target', '_blank');
  await expect(termsLink).toHaveAttribute('rel', /noopener/);
  await expect(termsLink).toHaveAttribute('rel', /noreferrer/);
  const privacyLink = page.getByRole('link', { name: '개인정보 처리 안내 보기' });
  await expect(privacyLink).toHaveAttribute('href', '/privacy');
  await expect(privacyLink).toHaveAttribute('target', '_blank');
  await expect(privacyLink).toHaveAttribute('rel', /noopener/);
  await expect(privacyLink).toHaveAttribute('rel', /noreferrer/);

  const policyPagePromise = page.waitForEvent('popup');
  await termsLink.click();
  const policyPage = await policyPagePromise;
  await expect(policyPage).toHaveURL(/\/terms$/);
  await policyPage.close();
  await expect(page.getByLabel('이름')).toHaveValue('동의확인');
  await expect(page.getByText('4 / 4 단계', { exact: true })).toBeVisible();

  await page.getByText('개인정보 수집·이용 내용 보기', { exact: true }).click();
  await expect(page.getByText('이메일, 비밀번호, 이름, 전화번호, 생년월일, 성별')).toBeVisible();
  await expect(page.getByText('회원 식별, 본인 확인, 고객 상담 및 서비스 제공')).toBeVisible();
  await expect(
    page.getByText('회원 탈퇴 시까지 또는 관련 법령에 따른 보관 기간'),
  ).toBeVisible();

  const submit = page.getByRole('button', { name: '회원가입 완료' });
  await expect(submit).toBeDisabled();
  for (const name of REQUIRED_CONSENTS) {
    await page.getByRole('checkbox', { name }).check();
  }
  await expect(submit).toBeEnabled();

  for (const name of REQUIRED_CONSENTS) {
    const checkbox = page.getByRole('checkbox', { name });
    await checkbox.uncheck();
    await expect(submit).toBeDisabled();
    await checkbox.check();
    await expect(submit).toBeEnabled();
  }
});

test('만 14세 미만이면 연령 확인 체크를 해제하고 가입 제한 메시지를 보여준다', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-09-08T12:00:00+09:00'));
  await openProfileStep(page, '2012-09-09');
  const ageTerms = page.getByRole('checkbox', { name: /만 14세 이상이에요/ });
  await ageTerms.click();

  await expect(ageTerms).not.toBeChecked();
  await expect(page.getByText('만14세 이상 가입이 가능합니다.')).toBeVisible();
});

test('동의한 서비스 이용약관 값은 기존 회원가입 API 필드로 전달된다', async ({ page }) => {
  let signupBody: Record<string, unknown> | undefined;
  await page.route('**/api/v1/auth/signup', async (route) => {
    signupBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '회원가입이 성공적으로 완료되었습니다.' }),
    });
  });
  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'consent-access-token' }),
    });
  });
  await openProfileStep(page);
  await checkAllRequiredConsents(page);

  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect.poll(() => signupBody).toBeDefined();
  expect(signupBody?.is_terms_agreed).toBe(true);
});
