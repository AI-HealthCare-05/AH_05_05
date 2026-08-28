import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { normalizePhoneNumber } from '@/shared/lib/phoneNumber';
import {
  mockChangePassword,
  mockCreateAccount,
  mockGetMyProfile,
  mockUpdateMyProfile,
} from './api.mock';
import type {
  AccountProfile,
  ChangePasswordPayload,
  CreateAccountPayload,
  Gender,
  UpdateAccountProfilePayload,
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
 * 사용자 API 는 snake_case 를 쓴다(관리자 API 는 CamelModel 이라 camelCase 다).
 * 공통 변환기를 두면 다른 엔티티까지 영향이 가므로 여기서만 맞춘다.
 *
 * 생년월일·성별은 가입 때 선택 항목이라 기존 회원은 null 로 온다.
 */
interface UserProfileResponse {
  name: string;
  phone_number: string | null;
  birth_date: string | null;
  gender: 'MALE' | 'FEMALE' | null;
}

function toAccountProfile(body: UserProfileResponse): AccountProfile {
  return {
    name: body.name,
    phoneNumber: body.phone_number ?? '',
    birthDate: body.birth_date ?? '',
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
    phone_number: normalizedPayload.phoneNumber,
    birth_date: normalizedPayload.birthDate,
    gender: normalizedPayload.gender === 'female' ? 'FEMALE' : 'MALE',
  });
  return toAccountProfile(body);
}

export async function changePassword(payload: ChangePasswordPayload): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    return mockChangePassword(payload);
  }
  return http.patch<void>('/v1/me/password', payload);
}
