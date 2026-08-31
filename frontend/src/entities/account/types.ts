export type Gender = 'male' | 'female';

/** DB `user.name` 컬럼(varchar 100)에 맞춘 상한. 서버 DTO 도 같은 값을 쓴다. */
export const NAME_MAX_LENGTH = 100;

export interface AccountProfile {
  name: string;
  phoneNumber: string;
  birthDate: string;
  gender: Gender;
}

export interface CreateAccountPayload extends AccountProfile {
  email: string;
  password: string;
}

export type UpdateAccountProfilePayload = AccountProfile;

export interface ChangePasswordPayload {
  currentPassword: string;
  newPassword: string;
}

export interface WithdrawAccountPayload {
  password: string;
}
