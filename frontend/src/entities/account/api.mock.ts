import { ApiError } from '@/shared/api/client';
import type {
  AccountProfile,
  ChangePasswordPayload,
  CreateAccountPayload,
  UpdateAccountProfilePayload,
  WithdrawAccountPayload,
} from './types';

let currentProfile: AccountProfile = {
  name: 'RxVita사용자',
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

/**
 * 실서버 `PATCH /v1/users/me/password` 의 오류 계약을 그대로 흉내냅니다.
 *
 * code 와 field 가 다르면 화면이 문구를 엉뚱한 칸에 붙입니다
 * (PasswordChangeSheet 의 errorTarget 이 이 둘로 칸을 고릅니다).
 */
export function mockChangePassword(payload: ChangePasswordPayload): void {
  if (payload.currentPassword !== currentPassword) {
    throw new ApiError(400, 'INVALID_PASSWORD', '현재 비밀번호가 맞지 않아요.');
  }
  if (payload.newPassword === currentPassword) {
    throw new ApiError(400, 'SAME_AS_CURRENT', '현재 비밀번호와 다른 비밀번호를 입력해주세요.');
  }
  // 서버는 validate_password 로 검사하고 422 에 field 를 실어 보냅니다.
  if (payload.newPassword.length < 8) {
    // field 는 보낸 표기법을 그대로 돌려준다. 지금은 camelCase 로 보낸다(#172).
    throw new ApiError(422, 'VALIDATION_ERROR', '비밀번호는 8자 이상이어야 합니다.', 'newPassword');
  }
  currentPassword = payload.newPassword;
}

/** 실서버 `DELETE /v1/users/me` 의 오류 계약을 그대로 흉내냅니다. */
export function mockWithdrawAccount({ password }: WithdrawAccountPayload): void {
  if (password !== currentPassword) {
    throw new ApiError(400, 'INVALID_PASSWORD', '비밀번호가 일치하지 않아요.');
  }
}
