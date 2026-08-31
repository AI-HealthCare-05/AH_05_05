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

/**
 * `type="text"` 로 쓰는 이메일 칸의 형식 검증.
 *
 * `type="email"` 을 못 쓴다. 크롬은 그 타입에서 도메인을 퓨니코드로 바꿔 `.value` 로 준다.
 * 화면에는 `ddadf한글` 이 보이는데 값은 `xn--ddadf-...` 라 한글을 걸러낼 수가 없다.
 * 대신 브라우저 기본 검증을 잃지 않도록 HTML 명세의 이메일 정규식을 그대로 pattern 에 준다.
 * (명세 정규식이라 ASCII 만 통과한다. 한글이 남더라도 제출 단계에서 한 번 더 걸린다.)
 */
export const EMAIL_INPUT_PATTERN =
  "[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*";
