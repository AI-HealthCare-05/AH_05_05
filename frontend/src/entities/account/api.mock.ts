import { ApiError } from '@/shared/api/client';
import type {
  AccountProfile,
  ChangePasswordPayload,
  CreateAccountPayload,
  UpdateAccountProfilePayload,
} from './types';

let currentProfile: AccountProfile = {
  name: '포케 사용자',
  phoneNumber: '01012345678',
  birthDate: '1980-08-02',
  gender: 'female',
};
let currentPassword = 'password1234';

export function mockCreateAccount(payload: CreateAccountPayload): AccountProfile {
  currentProfile = {
    name: payload.name,
    phoneNumber: payload.phoneNumber,
    birthDate: payload.birthDate,
    gender: payload.gender,
  };
  currentPassword = payload.password;
  return { ...currentProfile };
}

export function mockGetMyProfile(): AccountProfile {
  return { ...currentProfile };
}

export function mockUpdateMyProfile(payload: UpdateAccountProfilePayload): AccountProfile {
  currentProfile = { ...payload };
  return { ...currentProfile };
}

export function mockChangePassword(payload: ChangePasswordPayload): void {
  if (payload.currentPassword !== currentPassword) {
    throw new ApiError(
      400,
      'invalid_current_password',
      '현재 비밀번호가 맞지 않아요.',
      'currentPassword',
    );
  }
  currentPassword = payload.newPassword;
}
