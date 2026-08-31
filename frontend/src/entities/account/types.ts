export type Gender = 'male' | 'female';

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
