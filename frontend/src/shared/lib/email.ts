/** DB `user.email` 컬럼(varchar 255)에 맞춘 상한. 서버 DTO 도 같은 값을 쓴다. */
export const EMAIL_MAX_LENGTH = 255;

/**
 * 이메일에 쓸 수 없는 문자.
 *
 * 허용 범위를 ASCII 출력 가능 문자(공백 제외)로 잡아 한글·한자·이모지·공백을 한 번에 걸러낸다.
 * 한글 IME 로 타이핑하면 조합 중인 자모가 그대로 value 에 들어오므로,
 * 제출 시점이 아니라 입력 시점에 지워야 화면에 한글이 남지 않는다.
 */
const NOT_ALLOWED_IN_EMAIL = /[^!-~]/g;

/** 입력값에서 이메일에 못 쓰는 문자를 지우고 컬럼 폭까지 자른다. */
export function sanitizeEmailInput(value: string): string {
  return value.replace(NOT_ALLOWED_IN_EMAIL, '').slice(0, EMAIL_MAX_LENGTH);
}
