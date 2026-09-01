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
 * 로그인 실패 코드. 메시지는 서버가 준 문구를 그대로 띄우므로 코드로 문구를 만들지 마세요.
 *
 * - `INVALID_CREDENTIALS` (400) — **모든 실패가 이 하나입니다.**
 *   계정 없음·비밀번호 불일치·정지·탈퇴·대기를 구분하지 않습니다.
 *   구분하면 그 이메일의 가입 여부가 새어나갑니다(#196).
 *
 * 예전에는 비활성 계정에 `ACCOUNT_INACTIVE`(423)가 따로 있었습니다. 상태 코드만으로
 * 구분이 가능해 없앴습니다. 관리자 로그인은 이 규칙을 따르지 않습니다(내부용).
 */
export type LoginErrorCode = 'INVALID_CREDENTIALS';
