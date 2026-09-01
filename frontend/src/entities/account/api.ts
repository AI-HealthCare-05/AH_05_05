import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { normalizePhoneNumber } from '@/shared/lib/phoneNumber';
import {
  mockChangePassword,
  mockCreateAccount,
  mockGetMyProfile,
  mockUpdateMyProfile,
  mockWithdrawAccount,
} from './api.mock';
import type {
  AccountProfile,
  ChangePasswordPayload,
  CreateAccountPayload,
  Gender,
  UpdateAccountProfilePayload,
  WithdrawAccountPayload,
} from './types';

interface SignupResponseBody {
  detail: string;
}

export async function createAccount(payload: CreateAccountPayload): Promise<void> {
  const normalizedPayload = {
    ...payload,
    email: payload.email.trim(),
    name: payload.name.trim(),
    phoneNumber: normalizePhoneNumber(payload.phoneNumber),
  };
  if (USE_MOCK) {
    await mockDelay();
    mockCreateAccount(normalizedPayload);
    return;
  }
  // 회원가입만 아직 snake_case 다(#172 2차 범위). 「내 정보」 세 창구는 camelCase 로
  // 옮겼지만 auth 는 로그인까지 걸려 있어 따로 뗐다. 같은 파일에서 규칙이 갈리니 주의.
  await http.post<SignupResponseBody>('/v1/auth/signup', {
    email: normalizedPayload.email,
    password: normalizedPayload.password,
    name: normalizedPayload.name,
    phone_number: normalizedPayload.phoneNumber,
    birth_date: normalizedPayload.birthDate,
    gender: normalizedPayload.gender === 'male' ? 'MALE' : 'FEMALE',
    // AuthPage는 두 필수 동의가 모두 체크된 경우에만 createAccount를 호출합니다.
    is_terms_agreed: true,
  });
}

/**
 * 마이페이지 「기본정보」 경로.
 *
 * `/v1/me` 가 아니다. user_router 의 prefix 가 `/users` 라 빼면 404 다.
 * (`/v1/me/settings` 는 별도 라우터라 접두사가 없다 — 헷갈리기 쉽다.)
 */
const MY_PROFILE_PATH = '/v1/users/me';

/**
 * 백엔드 `UserInfoResponse` 중 이 화면이 쓰는 부분.
 *
 * 「내 정보」 세 창구는 camelCase 다(#172). 키 이름은 그대로 받고, 아래에서는
 * 값 모양만 화면에 맞춘다.
 *
 * 생년월일·성별은 가입 때 선택 항목이라 기존 회원은 null 로 온다.
 */
interface UserProfileResponse {
  name: string;
  phoneNumber: string | null;
  birthDate: string | null;
  gender: 'MALE' | 'FEMALE' | null;
}

/**
 * 서버 응답을 화면용 타입으로 바꾼다.
 *
 * 키 이름 매핑은 표기법이 같아져 사라졌지만, 값 변환은 남는다 —
 * null 을 빈 문자열로 바꾸는 것과 성별 대소문자다.
 */
function toAccountProfile(body: UserProfileResponse): AccountProfile {
  return {
    name: body.name,
    phoneNumber: body.phoneNumber ?? '',
    birthDate: body.birthDate ?? '',
    // 화면은 소문자를 쓴다(GenderRadioGroup). 값이 없으면 라디오를 비워 두고,
    // 사용자가 고르기 전까지 저장 버튼이 잠긴다(MyProfilePage 의 changed 계산).
    gender: body.gender === 'FEMALE' ? 'female' : body.gender === 'MALE' ? 'male' : ('' as Gender),
  };
}

export async function getMyProfile(): Promise<AccountProfile> {
  if (USE_MOCK) {
    await mockDelay();
    return mockGetMyProfile();
  }
  return toAccountProfile(await http.get<UserProfileResponse>(MY_PROFILE_PATH));
}

export async function updateMyProfile(
  payload: UpdateAccountProfilePayload,
): Promise<AccountProfile> {
  const normalizedPayload = {
    ...payload,
    name: payload.name.trim(),
    phoneNumber: normalizePhoneNumber(payload.phoneNumber),
  };
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateMyProfile(normalizedPayload);
  }
  // 보낸 항목만 바뀐다(서버가 exclude_none). 이메일은 이 화면에서 다루지 않으므로 넣지 않는다.
  const body = await http.patch<UserProfileResponse>(MY_PROFILE_PATH, {
    name: normalizedPayload.name,
    phoneNumber: normalizedPayload.phoneNumber,
    birthDate: normalizedPayload.birthDate,
    gender: normalizedPayload.gender === 'female' ? 'FEMALE' : 'MALE',
  });
  return toAccountProfile(body);
}

export async function changePassword(payload: ChangePasswordPayload): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    return mockChangePassword(payload);
  }
  // 조회·수정·탈퇴와 같은 user 리소스라 `/v1/users/me` 아래다.
  // (`/v1/me/settings` 는 user_settings 라는 다른 테이블이라 경로가 따로다.)
  return http.patch<void>(`${MY_PROFILE_PATH}/password`, {
    currentPassword: payload.currentPassword,
    newPassword: payload.newPassword,
  });
}

export async function withdrawAccount(payload: WithdrawAccountPayload): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    return mockWithdrawAccount(payload);
  }
  return http.delete<void>('/v1/users/me', payload);
}
