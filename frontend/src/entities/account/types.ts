export type Gender = 'male' | 'female';

export interface AccountProfile {
  birthDate: string;
  gender: Gender;
}

export interface CreateAccountPayload extends AccountProfile {
  email: string;
  password: string;
}
