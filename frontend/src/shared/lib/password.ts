/**
 * 비밀번호 입력 상한.
 *
 * DB 에는 해시가 저장되므로 컬럼 폭과는 무관하다. 화면에서 받아야 할 길이 기준이다.
 * 서버의 공통 검증기(validate_password)도 같은 값을 쓴다 — 사용자·관리자 공통이다.
 *
 * **「새로 정하는 비밀번호」에만 건다.** 로그인·탈퇴 확인·비밀번호 변경의 *현재* 비밀번호처럼
 * 대조용으로 받는 칸에는 절대 걸지 않는다. 이 정책이 생기기 전에 더 긴 비밀번호로 가입한
 * 계정이 로그인·탈퇴·변경 자체를 못 하게 된다.
 */
export const PASSWORD_MAX_LENGTH = 30;
export const PASSWORD_MIN_LENGTH = 8;

const PASSWORD_CHARACTER_RULES: ReadonlyArray<[RegExp, string]> = [
  [/[A-Z]/, '대문자'],
  [/[a-z]/, '소문자'],
  [/[0-9]/, '숫자'],
  [/[^a-zA-Z0-9]/, '특수문자'],
];

/** 새로 설정하는 비밀번호를 백엔드와 같은 기준으로 검증합니다. */
export function validatePassword(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `비밀번호는 ${PASSWORD_MIN_LENGTH}자 이상이어야 합니다.`;
  }
  if (password.length > PASSWORD_MAX_LENGTH) {
    return `비밀번호는 ${PASSWORD_MAX_LENGTH}자 이하여야 합니다.`;
  }

  const missing = PASSWORD_CHARACTER_RULES.filter(([pattern]) => !pattern.test(password)).map(
    ([, label]) => label,
  );
  return missing.length > 0
    ? `비밀번호에 ${missing.join(', ')}를 각각 1개 이상 포함해야 합니다.`
    : null;
}
