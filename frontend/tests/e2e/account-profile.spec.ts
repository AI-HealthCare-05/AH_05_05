import { expect, test, type Page } from 'playwright/test';

async function openSignup(page: Page) {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입' }).click();
}

async function fillSignupBase(page: Page) {
  await page.getByLabel('이메일').fill('new-patient@example.com');
  await page.getByLabel('비밀번호', { exact: true }).fill('password1234');
  await page.getByLabel('비밀번호 확인').fill('password1234');
  await page.getByLabel('이름').fill('신동훈');
  await page.getByLabel('전화번호').fill('01012345678');
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
}

test('회원가입은 비밀번호 확인 다음에 이름과 전화번호를 필수로 받는다', async ({ page }) => {
  await openSignup(page);

  const passwordConfirm = page.getByLabel('비밀번호 확인');
  const name = page.getByLabel('이름');
  const phoneNumber = page.getByLabel('전화번호');
  const birthDate = page.getByLabel('생년월일');

  await expect(name).toHaveAttribute('required', '');
  await expect(phoneNumber).toHaveAttribute('required', '');
  await expect(phoneNumber).toHaveAttribute('inputmode', 'tel');

  const passwordConfirmBox = await passwordConfirm.boundingBox();
  const nameBox = await name.boundingBox();
  const phoneNumberBox = await phoneNumber.boundingBox();
  const birthDateBox = await birthDate.boundingBox();
  expect(passwordConfirmBox).not.toBeNull();
  expect(nameBox).not.toBeNull();
  expect(phoneNumberBox).not.toBeNull();
  expect(birthDateBox).not.toBeNull();
  expect(passwordConfirmBox!.y).toBeLessThan(nameBox!.y);
  expect(nameBox!.y).toBeLessThan(phoneNumberBox!.y);
  expect(phoneNumberBox!.y).toBeLessThan(birthDateBox!.y);
});

test('회원가입 전화번호는 읽기 쉬운 형식으로 바꾸고 잘못된 번호는 인라인으로 막는다', async ({
  page,
}) => {
  await openSignup(page);
  await fillSignupBase(page);

  const phoneNumber = page.getByLabel('전화번호');
  await expect(phoneNumber).toHaveValue('010-1234-5678');

  await phoneNumber.fill('021234');
  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect(page.getByText('휴대전화 번호를 확인해 주세요.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('회원가입은 생년월일 다음에 기본 선택 없는 성별을 필수로 받는다', async ({ page }) => {
  await openSignup(page);
  const birthDate = page.getByLabel('생년월일');
  const male = page.getByRole('radio', { name: '남성' });
  const female = page.getByRole('radio', { name: '여성' });

  await expect(birthDate).toHaveAttribute('type', 'date');
  await expect(birthDate).toHaveAttribute('min', '1900-01-01');
  await expect(birthDate).toHaveAttribute('max', '2026-08-25');
  await expect(birthDate).toHaveAttribute('required', '');
  await expect(male).toHaveAttribute('required', '');
  await expect(female).toHaveAttribute('required', '');
  await expect(male).not.toBeChecked();
  await expect(female).not.toBeChecked();

  const passwordConfirmBox = await page.getByLabel('비밀번호 확인').boundingBox();
  const birthDateBox = await birthDate.boundingBox();
  const genderBox = await page.getByRole('group', { name: '성별' }).boundingBox();
  const termsBox = await page.getByText('필수 동의', { exact: true }).boundingBox();
  expect(passwordConfirmBox).not.toBeNull();
  expect(birthDateBox).not.toBeNull();
  expect(genderBox).not.toBeNull();
  expect(termsBox).not.toBeNull();
  expect(passwordConfirmBox!.y).toBeLessThan(birthDateBox!.y);
  expect(birthDateBox!.y).toBeLessThan(genderBox!.y);
  expect(genderBox!.y).toBeLessThan(termsBox!.y);
});

test('만 14세 미만은 보호자 안내와 함께 가입을 막는다', async ({ page }) => {
  await openSignup(page);
  await fillSignupBase(page);
  await page.getByLabel('생년월일').fill('2012-08-26');
  await page.getByRole('radio', { name: '여성' }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect(page.getByText('만 14세 미만은 보호자와 함께 가입해주세요.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('정확히 만 14세인 생일에는 생년월일과 성별을 저장하고 가입한다', async ({ page }) => {
  await openSignup(page);
  await fillSignupBase(page);
  await page.getByLabel('생년월일').fill('2012-08-25');
  await page.getByRole('radio', { name: '남성' }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();

  await expect(page).toHaveURL(/\/home$/);
  await expect
    .poll(() =>
      page.evaluate(() => ({
        token: sessionStorage.getItem('poke.access-token'),
        principal: sessionStorage.getItem('poke.account-principal'),
      })),
    )
    .toEqual({ token: 'mock-access-token', principal: 'new-patient@example.com' });
});

test('미래 생년월일과 일치하지 않는 비밀번호 확인으로 가입할 수 없다', async ({ page }) => {
  await openSignup(page);
  await fillSignupBase(page);
  await page.getByLabel('생년월일').fill('2026-08-26');
  await page.getByRole('radio', { name: '남성' }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel('생년월일').fill('1990-01-01');
  await page.getByLabel('비밀번호 확인').fill('different-password');
  await page.getByRole('button', { name: '회원가입 완료' }).click();
  await expect(page.getByText('비밀번호가 일치하지 않아요.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('마이페이지의 기본정보에서 가입 때 저장한 생년월일과 성별을 수정한다', async ({ page }) => {
  await openSignup(page);
  await fillSignupBase(page);
  await page.getByLabel('생년월일').fill('1991-03-15');
  await page.getByRole('radio', { name: '남성' }).check();
  await page.getByRole('button', { name: '회원가입 완료' }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.getByRole('button', { name: '마이', exact: true }).click();
  await page.getByRole('button', { name: /기본정보/ }).click();
  await expect(page).toHaveURL(/\/my\/profile$/);
  await expect(page.getByRole('heading', { name: '기본정보 수정' })).toBeVisible();
  await expect(page.getByLabel('이름')).toHaveValue('신동훈');
  await expect(page.getByLabel('전화번호')).toHaveValue('010-1234-5678');
  await expect(page.getByLabel('생년월일')).toHaveValue('1991-03-15');
  await expect(page.getByRole('radio', { name: '남성' })).toBeChecked();
  await expect(page.getByRole('button', { name: '저장', exact: true })).toBeDisabled();

  await page.getByLabel('전화번호').fill('01098765432');
  await page.getByLabel('생년월일').fill('1991-04-16');
  await expect(page.getByRole('button', { name: '저장', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByText('기본정보를 저장했어요.')).toBeVisible();
  await expect(page).toHaveURL(/\/my\/profile$/);
  await expect(page.getByLabel('전화번호')).toHaveValue('010-9876-5432');
  await expect(page.getByRole('button', { name: '저장', exact: true })).toBeDisabled();
});

test('기본정보에서도 공용 만 14세 검증을 적용한다', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-25T12:00:00+09:00'));
  await page.goto('/dev/my-profile');
  await page.getByLabel('생년월일').fill('2012-08-26');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  await expect(page.getByText('만 14세 미만은 보호자와 함께 가입해주세요.')).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('기본정보 입력창도 회원가입과 같은 DB 컬럼 폭을 지킨다', async ({ page }) => {
  await page.goto('/dev/my-profile');

  // 회원가입과 같은 user.name(varchar 100) · user.phone 에 쓰는 값이다.
  // 한쪽만 막아두면 어느 화면으로 고치느냐에 따라 동작이 갈린다.
  await expect(page.getByLabel('이름')).toHaveAttribute('maxlength', '100');
  await expect(page.getByLabel('전화번호')).toHaveAttribute('maxlength', '13');

  await page.getByLabel('이름').fill('가'.repeat(130));
  await expect(page.getByLabel('이름')).toHaveValue('가'.repeat(100));
});

test('기본정보 저장 실패는 화면 전환 없이 ErrorDialog로 알린다', async ({ page }) => {
  await page.goto('/dev/my-profile-save-error');
  await page.getByLabel('생년월일').fill('1981-08-02');
  await page.getByRole('button', { name: '저장', exact: true }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: '기본정보를 저장하지 못했어요' })).toBeVisible();
  await expect(page).toHaveURL(/\/dev\/my-profile-save-error$/);
});

test('비밀번호 변경은 별도 시트에서 입력 오류를 인라인으로 보여준다', async ({ page }) => {
  await page.goto('/dev/my-profile');
  await expect(page.getByLabel('현재 비밀번호')).toHaveCount(0);
  await page.getByRole('button', { name: '비밀번호 변경' }).click();
  const sheet = page.getByRole('dialog');

  await expect(sheet.getByRole('heading', { name: '비밀번호 변경' })).toBeVisible();
  await sheet.getByLabel('현재 비밀번호').fill('wrong-password');
  await sheet.getByLabel('새 비밀번호', { exact: true }).fill('new-password1234');
  await sheet.getByLabel('새 비밀번호 확인').fill('new-password1234');
  await sheet.getByRole('button', { name: '변경', exact: true }).click();
  await expect(sheet.getByText('현재 비밀번호가 맞지 않아요.')).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
});

test('비밀번호 변경 오류는 잘못 입력한 칸 아래에 붙는다', async ({ page }) => {
  // 예전에는 서버가 어느 칸 문제인지 알려줘도 전부 「현재 비밀번호」 아래에 붙어서,
  // 새 비밀번호 정책 위반인데 엉뚱한 칸이 빨갛게 됐다.
  await page.goto('/dev/my-profile');
  await page.getByRole('button', { name: '비밀번호 변경' }).click();
  const sheet = page.getByRole('dialog');
  const current = sheet.getByLabel('현재 비밀번호');
  const next = sheet.getByLabel('새 비밀번호', { exact: true });

  /** 해당 입력칸에 연결된 오류 문구(Input 이 `${id}-error` 로 붙인다). */
  const errorOf = async (input: typeof current) => {
    const id = await input.getAttribute('id');
    const message = page.locator(`#${id}-error`);
    return (await message.count()) ? message.innerText() : '';
  };

  // 1) 새 비밀번호 정책 위반 -> 새 비밀번호 아래
  await current.fill('password1234');
  await next.fill('short');
  await sheet.getByLabel('새 비밀번호 확인').fill('short');
  await sheet.getByRole('button', { name: '변경', exact: true }).click();
  await expect.poll(() => errorOf(next)).toContain('8자 이상');
  expect(await errorOf(current)).toBe('');

  // 2) 현재 비밀번호 불일치 -> 현재 비밀번호 아래
  await current.fill('wrong-password');
  await next.fill('new-password1234');
  await sheet.getByLabel('새 비밀번호 확인').fill('new-password1234');
  await sheet.getByRole('button', { name: '변경', exact: true }).click();
  await expect.poll(() => errorOf(current)).toContain('현재 비밀번호가 맞지 않아요.');
  expect(await errorOf(next)).toBe('');
});

test('비밀번호 변경 성공은 시트를 닫고 토스트만 보여준다', async ({ page }) => {
  await page.goto('/dev/my-profile');
  await page.getByRole('button', { name: '비밀번호 변경' }).click();
  const sheet = page.getByRole('dialog');
  await sheet.getByLabel('현재 비밀번호').fill('password1234');
  await sheet.getByLabel('새 비밀번호', { exact: true }).fill('new-password1234');
  await sheet.getByLabel('새 비밀번호 확인').fill('new-password1234');
  await sheet.getByRole('button', { name: '변경', exact: true }).click();

  await expect(sheet).toBeHidden();
  await expect(page.getByText('비밀번호를 변경했어요.')).toBeVisible();
  await expect(page).toHaveURL(/\/dev\/my-profile$/);
});
