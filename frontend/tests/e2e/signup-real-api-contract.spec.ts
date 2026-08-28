import { expect, test } from 'playwright/test';

test('실 API 회원가입은 명세 요청을 보내고 로그인 성공 뒤 홈으로 이동한다', async ({ page }) => {
  let signupBody: unknown;
  let loginBody: unknown;

  await page.route('**/api/v1/auth/signup', async (route) => {
    signupBody = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '회원가입이 성공적으로 완료되었습니다.' }),
    });
  });
  await page.route('**/api/v1/auth/login', async (route) => {
    loginBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'signup-access-token' }),
    });
  });

  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();
  await page.getByLabel('이메일').fill('new-patient@example.com');
  await page.getByLabel('비밀번호', { exact: true }).fill('Password123!');
  await page.getByLabel('비밀번호 확인').fill('Password123!');
  await page.getByLabel('이름').fill(' 신규 사용자 ');
  await page.getByLabel('전화번호').fill('011-123-4567');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect(page).toHaveURL(/\/home$/);
  expect(signupBody).toEqual({
    email: 'new-patient@example.com',
    password: 'Password123!',
    name: '신규 사용자',
    phone_number: '0111234567',
    birth_date: '1990-01-01',
    gender: 'FEMALE',
    is_terms_agreed: true,
  });
  expect(loginBody).toEqual({
    email: 'new-patient@example.com',
    password: 'Password123!',
  });
  await expect
    .poll(() => page.evaluate(() => sessionStorage.getItem('poke.access-token')))
    .toBe('signup-access-token');
});

test('회원가입 입력창은 DB 컬럼 폭까지만 받는다', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();

  // user.email 은 varchar(255), user.name 은 varchar(100) 이다.
  await expect(page.getByLabel('이메일')).toHaveAttribute('maxlength', '255');
  await expect(page.getByLabel('이름')).toHaveAttribute('maxlength', '100');
  await expect(page.getByLabel('전화번호')).toHaveAttribute('maxlength', '13');

  await page.getByLabel('이름').fill('가'.repeat(120));
  await expect(page.getByLabel('이름')).toHaveValue('가'.repeat(100));
});

test('회원가입 이메일 API 검증 오류는 브라우저 검증 말풍선으로 안내한다', async ({ page }) => {
  await page.route('**/api/v1/auth/signup', async (route) => {
    await route.fulfill({
      status: 422,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 'VALIDATION_ERROR',
        message:
          'value is not a valid email address: The part after the @-sign is not valid. It should have a period.',
        field: 'email',
      }),
    });
  });

  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();
  const emailInput = page.getByLabel('이메일');
  await emailInput.fill('patient@localhost');
  await page.getByLabel('비밀번호', { exact: true }).fill('Password123!');
  await page.getByLabel('비밀번호 확인').fill('Password123!');
  await page.getByLabel('이름').fill('테스트 회원');
  await page.getByLabel('전화번호').fill('010-1234-5678');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect
    .poll(() => emailInput.evaluate((input: HTMLInputElement) => input.validationMessage))
    .toBe('이메일 주소를 확인해주세요');
  await expect(page.getByText(/value is not a valid email address/)).toHaveCount(0);
});
