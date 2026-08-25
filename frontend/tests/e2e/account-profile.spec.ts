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
  await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
}

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
