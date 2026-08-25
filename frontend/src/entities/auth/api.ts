import { http, mockDelay, setAccessToken } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import type { LoginPayload, LoginResponse } from './types';

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  if (USE_MOCK) {
    await mockDelay();
    return { accessToken: 'mock-session-token' };
  }
  const response = await http.post<{ access_token: string }>('/v1/auth/login', payload);
  setAccessToken(response.access_token);
  return { accessToken: response.access_token };
}
