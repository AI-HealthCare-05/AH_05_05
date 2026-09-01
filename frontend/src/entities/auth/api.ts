/** 인증 API. 화면은 이 함수들만 부릅니다. */
import { http, mockDelay, setAccessToken } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockLogin } from './api.mock';
import type { LoginPayload, LoginResult } from './types';

/** 백엔드 응답 원형. 이 엔드포인트만 아직 snake_case 입니다. */
interface LoginResponseBody {
  access_token: string;
}

/**
 * 로그인하고 액세스 토큰을 클라이언트에 심습니다.
 *
 * 토큰은 메모리에만 둡니다(유저플로우 v4). 새로고침하면 사라져 다시 로그인해야 합니다.
 * 리프레시 토큰은 쓰지 않습니다 — 백엔드도 기본적으로 발급하지 않습니다.
 *
 * 실패는 ApiError 로 던져집니다. 화면은 message 를 그대로 띄웁니다.
 * 실패 코드는 INVALID_CREDENTIALS 하나뿐이라 분기할 것이 없습니다 — 계정 상태를
 * 구분해 알려주지 않기 때문입니다(#196).
 */
export async function login(payload: LoginPayload): Promise<LoginResult> {
  if (USE_MOCK) {
    await mockDelay();
    const result = mockLogin();
    setAccessToken(result.accessToken);
    return result;
  }
  const body = await http.post<LoginResponseBody>('/v1/auth/login', payload);
  setAccessToken(body.access_token);
  return { accessToken: body.access_token };
}

/** 로그아웃. 서버에 상태가 없으므로 메모리의 토큰만 비웁니다. */
export function logout(): void {
  setAccessToken(null);
}
