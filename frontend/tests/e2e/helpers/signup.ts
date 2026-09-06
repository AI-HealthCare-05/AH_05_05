import type { Page } from 'playwright/test';

export type SignupGender = '남성' | '여성';

export interface SignupCredentials {
  email?: string;
  password?: string;
  verificationCode?: string;
}

export interface SignupProfile {
  name?: string;
  phoneNumber?: string;
  birthDate?: string;
  gender?: SignupGender;
  recordTerms?: boolean;
  aiTerms?: boolean;
}

export interface SignupValues extends SignupCredentials, SignupProfile {}

const DEFAULT_CREDENTIALS: Required<SignupCredentials> = {
  email: 'new-patient@example.com',
  password: 'password1234',
  verificationCode: '123456',
};

const DEFAULT_BASE_PROFILE: Required<Pick<SignupProfile, 'name' | 'phoneNumber'>> = {
  name: '신동훈',
  phoneNumber: '01012345678',
};

export async function openSignup(page: Page, fixedTime?: Date): Promise<void> {
  if (fixedTime) await page.clock.setFixedTime(fixedTime);
  await page.goto('/login');
  await page.getByRole('button', { name: '회원가입', exact: true }).click();
}

/** 이메일·인증코드를 지나 비밀번호 단계까지 엽니다. */
export async function advanceSignupToPassword(
  page: Page,
  credentials: SignupCredentials = {},
): Promise<void> {
  const values = { ...DEFAULT_CREDENTIALS, ...credentials };
  await page.getByLabel('이메일').fill(values.email);
  await page.getByRole('button', { name: '인증코드 받기' }).click();
  await page.getByLabel('인증코드').fill(values.verificationCode);
  await page.getByRole('button', { name: '확인' }).click();
}

/** 이메일·인증코드·비밀번호를 지나 프로필 단계까지 엽니다. */
export async function advanceSignupToProfile(
  page: Page,
  credentials: SignupCredentials = {},
): Promise<void> {
  const values = { ...DEFAULT_CREDENTIALS, ...credentials };
  await advanceSignupToPassword(page, values);
  await page.getByLabel('비밀번호', { exact: true }).fill(values.password);
  await page.getByLabel('비밀번호 확인', { exact: true }).fill(values.password);
  await page.getByRole('button', { name: '다음' }).click();
}

/** 프로필 단계에서 지정한 값만 채웁니다. 비워 둔 항목의 검증을 테스트할 때 사용합니다. */
export async function fillSignupProfile(page: Page, values: SignupProfile = {}): Promise<void> {
  if (values.name !== undefined) await page.getByLabel('이름').fill(values.name);
  if (values.phoneNumber !== undefined) await page.getByLabel('전화번호').fill(values.phoneNumber);
  if (values.birthDate !== undefined) await page.getByLabel('생년월일').fill(values.birthDate);
  if (values.gender !== undefined) await page.getByRole('radio', { name: values.gender }).check();
  if (values.recordTerms) {
    await page.getByRole('checkbox', { name: /진료기록 수집/ }).check();
  }
  if (values.aiTerms) {
    await page.getByRole('checkbox', { name: /AI 서비스 이용/ }).check();
  }
}

/** 기존 프로필 계약 테스트가 공통으로 쓰는 최소 가입 데이터입니다. */
export async function fillSignupBase(
  page: Page,
  overrides: SignupCredentials & SignupProfile = {},
): Promise<void> {
  await advanceSignupToProfile(page, overrides);
  await fillSignupProfile(page, {
    name: overrides.name ?? DEFAULT_BASE_PROFILE.name,
    phoneNumber: overrides.phoneNumber ?? DEFAULT_BASE_PROFILE.phoneNumber,
    recordTerms: overrides.recordTerms ?? true,
    aiTerms: overrides.aiTerms ?? true,
    birthDate: overrides.birthDate,
    gender: overrides.gender,
  });
}

export async function fillSignup(page: Page, values: SignupValues = {}): Promise<void> {
  await fillSignupBase(page, values);
  if (values.birthDate === undefined) {
    await page.getByLabel('생년월일').fill('1990-01-01');
  }
  if (values.gender === undefined) {
    await page.getByRole('radio', { name: '여성' }).check();
  }
}
