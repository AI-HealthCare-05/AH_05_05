export type Gender = 'male' | 'female';

/**
 * 입력 상한. DB 컬럼(varchar 100)보다 좁다 — 일부러 그렇다.
 *
 * 컬럼 폭은 저장 한계일 뿐이고, 화면에서 받아야 할 길이는 그보다 훨씬 짧다.
 * 서버 DTO(SignUpRequest.name, UserUpdateRequest.name)도 같은 값을 쓴다.
 */
export const NAME_MAX_LENGTH = 20;

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
