import { expect, test, type Page } from 'playwright/test';

test.setTimeout(20_000);

async function openSignup(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
}

test('회원가입은 이메일·인증코드·비밀번호·프로필 순서의 네 단계로 진행한다', async ({ page }) => {
  await openSignup(page);

  await expect(page.getByText('1 / 4 단계', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '이메일을 알려주세요' })).toBeVisible();
  await expect(page.getByRole('button', { name: '인증코드 받기' })).toBeDisabled();

  const email = page.getByLabel('이메일');
  await expect(email).toHaveAttribute('autocomplete', 'email');
  await email.fill('new-patient@example.com');
  await page.getByRole('button', { name: '인증코드 받기' }).click();

  await expect(page.getByText('2 / 4 단계', { exact: true })).toBeVisible();
  await expect(page.getByLabel('인증코드')).toHaveAttribute('maxlength', '6');
  await expect(page.getByLabel('남은 시간')).toHaveText(/\d{2}:\d{2}/);
  await expect(page.getByText('new-patient@example.com 으로 6자리 코드를 보냈어요.')).toBeVisible();
  await expect(page.getByLabel('이메일')).toHaveCount(0);

  await page.getByLabel('인증코드').fill('123456');
  await page.getByRole('button', { name: '확인' }).click();

  await expect(page.getByText('3 / 4 단계', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '비밀번호를 정해주세요' })).toBeVisible();
  await expect(page.getByLabel('이메일')).toHaveCount(0);

  await page.getByLabel('비밀번호', { exact: true }).fill('Password123!');
  await page.getByLabel('비밀번호 확인', { exact: true }).fill('Password123!');
  await page.getByRole('button', { name: '다음' }).click();

  await expect(page.getByText('4 / 4 단계', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '마지막이에요' })).toBeVisible();
  await expect(page.getByLabel('이메일')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '회원가입 완료' })).toBeDisabled();
});

test('회원가입 단계의 뒤로가기는 이전 단계로 돌아가고 이메일은 수정할 수 없다', async ({ page }) => {
  await openSignup(page);
  await page.getByLabel('이메일').fill('keep@example.com');
  await page.getByRole('button', { name: '인증코드 받기' }).click();
  await page.getByLabel('인증코드').fill('123456');
  await page.getByRole('button', { name: '확인' }).click();

  await expect(page.getByText('3 / 4 단계', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '뒤로 가기' }).click();

  await expect(page.getByText('2 / 4 단계', { exact: true })).toBeVisible();
  await expect(page.getByText('keep@example.com 으로 6자리 코드를 보냈어요.')).toBeVisible();
  await expect(page.getByLabel('이메일')).toHaveCount(0);
});

test('튜토리얼은 한 브라우저 세션에서 한 번만 보이고 건너뛰기는 홈으로 간다', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('약봉투를 찍으면')).toBeVisible({ timeout: 4_000 });
  await expect(page.getByText('1 / 4')).toHaveCount(0);
  await page.getByRole('button', { name: '건너뛰기' }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.goto('/');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('button', { name: '건너뛰기' })).toHaveCount(0);
});

test('튜토리얼 마지막 완료는 홈으로 이동하고 세션 표시를 남긴다', async ({ page }) => {
  await page.goto('/tutorial');

  await expect(page.getByText('약봉투를 찍으면')).toBeVisible();
  for (const title of ['먹을 시간에', '영양제 성분을', '내 약을 근거로']) {
    await page.getByRole('button', { name: '다음' }).click();
    await expect(page.getByText(title)).toBeVisible();
  }

  await page.getByRole('button', { name: '시작하기' }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.evaluate(() => sessionStorage.getItem('poke:tutorial-seen'))).resolves.toBe('true');
});

test('회원가입 완료는 기존 계정 생성 뒤 로그인 API 순서를 유지한다', async ({ page }) => {
  test.skip(process.env.VITE_USE_MOCK !== 'false', '실 API 계약 검증은 e2e-real 모드에서 실행합니다.');

  let signupBody: unknown;
  let loginBody: unknown;
  const requestOrder: string[] = [];
  // 홈 진입 뒤 부수 API가 계약 테스트를 방해하지 않도록, 인증 외 요청은 실패로 고정합니다.
  // 401은 세션을 지우므로 사용하지 않습니다.
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
  });
  await page.route('**/api/v1/auth/signup', async (route) => {
    requestOrder.push('signup');
    signupBody = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '회원가입이 성공적으로 완료되었습니다.' }),
    });
  });
  await page.route('**/api/v1/auth/login', async (route) => {
    requestOrder.push('login');
    loginBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'signup-access-token' }),
    });
  });

  await openSignup(page);
  await page.getByLabel('이메일').fill('new-patient@example.com');
  await page.getByRole('button', { name: '인증코드 받기' }).click();
  await page.getByLabel('인증코드').fill('123456');
  await page.getByRole('button', { name: '확인' }).click();
  await page.getByLabel('비밀번호', { exact: true }).fill('Password123!');
  await page.getByLabel('비밀번호 확인', { exact: true }).fill('Password123!');
  await page.getByRole('button', { name: '다음' }).click();
  await page.getByLabel('이름').fill('  신규사용자  ');
  await page.getByLabel('전화번호').fill('011-123-4567');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect
    .poll(() => page.evaluate(() => sessionStorage.getItem('poke.access-token')))
    .toBe('signup-access-token');
  await expect(page).toHaveURL(/\/home$/);
  expect(requestOrder).toEqual(['signup', 'login']);
  expect(signupBody).toEqual({
    email: 'new-patient@example.com',
    password: 'Password123!',
    name: '신규사용자',
    phone_number: '0111234567',
    birth_date: '1990-01-01',
    gender: 'FEMALE',
    is_terms_agreed: true,
  });
  expect(loginBody).toEqual({
    email: 'new-patient@example.com',
    password: 'Password123!',
  });
});
