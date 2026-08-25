import type { AccountProfile, CreateAccountPayload } from './types';

let currentProfile: AccountProfile = {
  birthDate: '1980-08-02',
  gender: 'female',
};

export function mockCreateAccount(payload: CreateAccountPayload): AccountProfile {
  currentProfile = {
    birthDate: payload.birthDate,
    gender: payload.gender,
  };
  return { ...currentProfile };
}
