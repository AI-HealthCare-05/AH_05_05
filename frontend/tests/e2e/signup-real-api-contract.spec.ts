import { expect, test } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});

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

test('이메일 pattern 은 브라우저가 실제로 컴파일하고 적용한다', async ({ page }) => {
  // 크롬은 pattern 을 v 플래그로 컴파일한다. 문자 클래스 안의 `/ { | }` 를 이스케이프하지
  // 않으면 컴파일에 실패하고 **속성이 통째로 무시된다**(#180). 잠금장치가 안 붙었는데
  // 아무도 모르던 것이 이번 문제의 본질이라, 붙었는지부터 확인한다.
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();
  const emailInput = page.getByLabel('이메일');

  expect(consoleErrors.filter((text) => text.includes('Pattern attribute value'))).toEqual([]);

  // 화면에 실제로 붙은 속성값을 그대로 컴파일해 본다. 상수를 import 해서 보면
  // 브라우저에 전달된 값이 아니라 소스를 검사하게 된다.
  const matches = await emailInput.evaluate((element: HTMLInputElement) => {
    const attribute = element.getAttribute('pattern') ?? '';
    // pattern 속성은 브라우저가 앞뒤에 ^(?: )$ 를 붙여 쓴다. 그대로 흉내낸다.
    const pattern = new RegExp(`^(?:${attribute})$`, 'v');
    return {
      korean: pattern.test('한글@example.com'),
      koreanDomain: pattern.test('a@한글.com'),
      plain: pattern.test('user@example.com'),
      punctuated: pattern.test("a.b'c+d@sub.example.co.kr"),
    };
  });
  expect(matches).toEqual({
    korean: false,
    koreanDomain: false,
    plain: true,
    punctuated: true,
  });

  // 브라우저가 실제로 막는지. 예전에는 checkValidity() 가 그냥 true 였다.
  await emailInput.fill('abc');
  expect(
    await emailInput.evaluate((element: HTMLInputElement) => element.validity.patternMismatch),
  ).toBe(true);

  await emailInput.fill('user@example.com');
  expect(await emailInput.evaluate((element: HTMLInputElement) => element.checkValidity())).toBe(
    true,
  );
});

test('회원가입 이메일 칸은 한글을 지우고 이유를 알린다', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();

  const emailInput = page.getByLabel('이메일');
  await emailInput.fill('한글주소@예시.한국');
  await expect(emailInput).toHaveValue('@.');
  await expect(page.getByText('이메일은 영문, 숫자와 기호만 입력할 수 있어요.')).toBeVisible();

  // 한글을 지운 뒤 정상 입력하면 안내 문구도 사라진다.
  await emailInput.fill('patient@example.com');
  await expect(emailInput).toHaveValue('patient@example.com');
  await expect(page.getByText('이메일은 영문, 숫자와 기호만 입력할 수 있어요.')).toHaveCount(0);
});

test('이메일 @ 뒤에 한글을 조합해도 앞서 입력한 주소가 남는다', async ({ page }) => {
  // type="email" 이던 시절 크롬이 도메인을 퓨니코드(xn--...)로 바꿔 값을 넘겨준 탓에
  // 화면에는 한글이 보이는데 코드는 ASCII 만 보고 통과시켰다. fill() 로는 재현되지 않아
  // CDP 로 실제 IME 조합을 흉내낸다.
  const cdp = await page.context().newCDPSession(page);
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();

  const emailInput = page.getByLabel('이메일');
  await emailInput.click();
  await page.keyboard.type('ddfdd@ddadf');

  // 조합 중인 글자는 IME 가 그리는 것이라 화면에 잠깐 보인다. 그건 막을 수 없다.
  // 여기서 확인할 것은 앞서 입력해 둔 영문이 그대로 붙어 있는가다.
  for (const composing of ['ㅇ', '오', '올']) {
    await cdp.send('Input.imeSetComposition', {
      text: composing,
      selectionStart: composing.length,
      selectionEnd: composing.length,
    });
    await expect(emailInput).toHaveValue(`ddfdd@ddadf${composing}`);
  }

  // 조합이 끝나면 한글만 사라지고 영문은 남는다.
  await cdp.send('Input.imeSetComposition', { text: '', selectionStart: 0, selectionEnd: 0 });
  await expect(emailInput).toHaveValue('ddfdd@ddadf');

  // 조합 뒤에도 입력이 얼지 않는다. (조합 상태를 플래그로 들고 있으면 여기서 막힌다)
  await page.keyboard.type('.net');
  await expect(emailInput).toHaveValue('ddfdd@ddadf.net');
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
