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

/**
 * 비밀번호에 쓸 수 없는 문자 — 한글만 지운다.
 *
 * 한글을 막는 이유는 두 가지가 겹친다.
 * 1. 아래 특수문자 규칙이 `[^a-zA-Z0-9]` 라 **한글이 「특수문자 1개 이상」 요건을 대신 채운다.**
 *    `비둘기23222Ok` 이 정책을 통과한다.
 * 2. bcrypt 는 72바이트까지만 해시에 반영한다. 한글은 UTF-8 로 글자당 3바이트라
 *    30자면 90바이트가 되어 초과분이 **오류 없이 잘린다.** PASSWORD_MAX_LENGTH 는
 *    글자 수 기준이라 이걸 막지 못한다.
 *
 * `email.ts` 의 NOT_ALLOWED_IN_EMAIL 처럼 ASCII 밖을 통째로 막지 **않는다.**
 * 한자·일본어·이모지·공백은 그대로 통과시킨다(#374 에서 정한 범위). 그래서 72바이트
 * 초과 경로는 남는다 — 별건으로 분리했다(#376).
 *
 * `\p{Script=Hangul}` 을 쓰는 이유: 한글은 여러 유니코드 블록에 흩어져 있어 범위를
 * 나열하면 빠뜨린다. 특히 **IME 조합 중에는 호환 자모(ㄱ~ㅣ)가 들어와서**, 완성형
 * (가~힣)만 막으면 `ㅂㅣㄷ` 같은 값이 남는다. 실측으로 확인한 커버리지는 아래와 같다.
 *   완성형 음절 · 호환 자모 · 첫가끝 자모 · 자모 확장 A/B · 반각 한글  → 모두 제거
 *   한자 · 일본어 · 이모지 · 공백 · 영문숫자특수                      → 모두 통과
 * `name.ts` 가 `\p{L}\p{M}` 로 유니코드 속성을 쓰는 것과 같은 방식이다.
 */
const HANGUL_IN_PASSWORD = /\p{Script=Hangul}/gu;

/**
 * 비밀번호 입력에서 한글을 지우고 입력 상한까지 자릅니다.
 *
 * `sanitizeEmailInput` 과 같이 **제거를 먼저 하고 자른다.** 순서가 바뀌면 지워질 글자가
 * 상한을 차지해 결과가 달라진다.
 *
 * ⚠️ 정규화(NFC 등)를 하지 않는다. `name.ts` 는 이름을 NFC 로 정규화하지만, 비밀번호는
 * 정규화하면 **해시 대상 문자열 자체가 바뀐다.** 이 함수는 새로 정하는 칸에만 걸고
 * 로그인 칸에는 걸지 않으므로, 여기서만 정규화하면 같은 키를 눌러도 대조가 어긋난다.
 *
 * **「새로 정하는 비밀번호」에만 쓴다.** 대조용으로 받는 칸(로그인·현재 비밀번호·탈퇴 확인)에
 * 쓰면 이미 한글 비밀번호로 가입한 계정이 로그인·변경·탈퇴를 못 하게 된다.
 * PASSWORD_MAX_LENGTH 와 같은 기준이다.
 */
export function sanitizePasswordInput(value: string): string {
  return value.replace(HANGUL_IN_PASSWORD, '').slice(0, PASSWORD_MAX_LENGTH);
}

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
