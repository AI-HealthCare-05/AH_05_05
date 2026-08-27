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

export async function getMyProfile(): Promise<AccountProfile> {
  if (USE_MOCK) {
    await mockDelay();
    return mockGetMyProfile();
  }
  return http.get<AccountProfile>('/v1/me');
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
  return http.patch<AccountProfile>('/v1/me', normalizedPayload);
}

export async function changePassword(payload: ChangePasswordPayload): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    return mockChangePassword(payload);
  }
  return http.patch<void>('/v1/me/password', payload);
}
