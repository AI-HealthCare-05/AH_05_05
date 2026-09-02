/** 서버 validate_name 과 같은 Unicode 문자 규칙이다. 한쪽만 고치면 안 된다. */
const NAME_PATTERN = /^[\p{L}\p{M}]+$/u;
const INVALID_NAME_CHARACTERS = /[^\p{L}\p{M}]/gu;

export const NAME_MIN_LENGTH = 2;

/**
 * 입력 상한. DB 컬럼(varchar 100)보다 좁다 — 일부러 그렇다.
 *
 * 컬럼 폭은 저장 한계일 뿐이고, 화면에서 받아야 할 길이는 그보다 훨씬 짧다.
 * 서버 DTO(SignUpRequest.name, UserUpdateRequest.name)도 같은 값을 쓴다.
 */
export const NAME_MAX_LENGTH = 20;

/** 회원가입 이름 입력에서 숫자·공백·문장부호·기호를 제거합니다. */
export function sanitizeNameInput(value: string): string {
  return value.normalize('NFC').replace(INVALID_NAME_CHARACTERS, '');
}

/**
 * 이름은 NFC 로 정규화하고 모든 언어의 문자와 결합 문자만 허용한다.
 * 입력 필터는 한글 IME 조합 중이 아니라 조합 완료 후 호출해야 한다.
 */
export function validateName(value: string): string | null {
  const name = value.normalize('NFC');
  if (name.length < NAME_MIN_LENGTH) return '이름을 두 글자 이상 입력해 주세요.';
  if (!NAME_PATTERN.test(name)) {
    return '이름에는 숫자, 공백, 특수문자를 사용할 수 없습니다.';
  }
  return null;
}
