import type { LoginResult } from './types';

/**
 * 목업 로그인. 아무 이메일·비밀번호나 통과시킵니다.
 *
 * 목업 모드에서는 다른 entities 도 전부 고정 데이터를 돌려주므로 토큰을 검사하는
 * 곳이 없습니다. 그래서 실패 경로를 흉내내지 않습니다 — 실패 문구와 423 분기는
 * VITE_USE_MOCK=false 로 두고 실제 백엔드에 붙여서 확인합니다.
 */
export function mockLogin(): LoginResult {
  return { accessToken: 'mock-access-token' };
}
