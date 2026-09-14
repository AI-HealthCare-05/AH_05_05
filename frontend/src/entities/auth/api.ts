/** 인증 API. 화면은 이 함수들만 부릅니다. */
import { endSession, http, mockDelay, setAccessToken } from '@/shared/api/client';
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
 * 액세스 토큰은 탭의 sessionStorage에, 리프레시 토큰은 HttpOnly 쿠키에 둡니다.
 * 웹앱에서 30분간 활동이 없으면 세션을 종료합니다.
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

/** 입력한 이메일 계정의 임시비밀번호 발송을 요청합니다. */
export async function requestPasswordReset(email: string): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    return;
  }
  await http.post('/v1/auth/password-reset', { email });
}

/** 로컬 인증을 즉시 종료하고 서버 리프레시 쿠키도 정리합니다. */
export function logout(): void {
  void endSession();
}
