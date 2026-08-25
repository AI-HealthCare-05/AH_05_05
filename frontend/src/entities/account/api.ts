import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
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

export async function createAccount(payload: CreateAccountPayload): Promise<AccountProfile> {
  if (USE_MOCK) {
    await mockDelay();
    return mockCreateAccount(payload);
  }
  return http.post<AccountProfile>('/v1/accounts', payload);
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
  if (USE_MOCK) {
    await mockDelay();
    return mockUpdateMyProfile(payload);
  }
  return http.patch<AccountProfile>('/v1/me', payload);
}

export async function changePassword(payload: ChangePasswordPayload): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    return mockChangePassword(payload);
  }
  return http.patch<void>('/v1/me/password', payload);
}
