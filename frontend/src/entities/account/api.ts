import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockCreateAccount } from './api.mock';
import type { AccountProfile, CreateAccountPayload } from './types';

export async function createAccount(payload: CreateAccountPayload): Promise<AccountProfile> {
  if (USE_MOCK) {
    await mockDelay();
    return mockCreateAccount(payload);
  }
  return http.post<AccountProfile>('/v1/accounts', payload);
}
