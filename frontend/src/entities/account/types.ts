export type Gender = 'male' | 'female';

export interface AccountProfile {
  name: string;
  maskedName: string;
  phoneNumber: string;
  birthDate: string;
  gender: Gender;
}

export interface CreateAccountPayload extends Omit<AccountProfile, 'maskedName'> {
  email: string;
  password: string;
}

export type UpdateAccountProfilePayload = Omit<AccountProfile, 'maskedName'>;

export interface ChangePasswordPayload {
  currentPassword: string;
  newPassword: string;
}

export interface WithdrawAccountPayload {
  password: string;
}
