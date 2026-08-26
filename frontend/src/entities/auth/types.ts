/** 로그인 요청. 백엔드 POST /api/v1/auth/login 이 그대로 받습니다. */
export interface LoginPayload {
  email: string;
  password: string;
}

/**
 * 로그인 성공 결과.
 *
 * 백엔드 응답 키는 `access_token`(snake_case)입니다. 다른 API 는 camelCase 인데
 * 이 엔드포인트만 아직 이관 전이라, api.ts 에서 변환해 화면에는 camelCase 로 넘깁니다.
 */
export interface LoginResult {
  accessToken: string;
}

/**
 * 로그인 실패 코드. 화면 분기가 필요할 때만 씁니다.
 * 메시지는 서버가 준 문구를 그대로 띄우므로 코드로 문구를 만들지 마세요.
 *
 * - `INVALID_CREDENTIALS` 이메일이 없거나 비밀번호가 틀림 (400).
 *   두 경우를 구분하지 않습니다 — 구분하면 가입 여부가 새어나갑니다
 * - `ACCOUNT_INACTIVE` 정지·탈퇴·대기 계정 (423).
 *   관리자 로그인은 403 을 쓰므로 코드가 다릅니다
 */
export type LoginErrorCode = 'INVALID_CREDENTIALS' | 'ACCOUNT_INACTIVE';
