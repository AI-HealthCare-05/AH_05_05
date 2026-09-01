/**
 * 이름에 쓸 수 있는 글자 — 한글 완성형과 영문 알파벳뿐.
 *
 * 공백을 허용하지 않는다. 「김 진형」처럼 띄어 쓰면 같은 사람이 두 가지로 저장돼
 * 관리자 콘솔 검색에서 갈린다. 영문 이름은 붙여 쓴다(KimJinhyeong).
 *
 * 낱자(ㄱ, ㅏ)를 막는다. 한글 IME 로 조합 중인 자모가 그대로 값에 들어오는데,
 * 조합이 끝나지 않은 채 제출하면 「ㅋㅋㅋ」 같은 값이 저장된다.
 *
 * 서버 validate_name 과 같은 규칙이다. 한쪽만 고치면 안 된다.
 */
const NAME_PATTERN = /^[가-힣a-zA-Z]+$/;

export const NAME_MIN_LENGTH = 2;

/**
 * 입력 상한. DB 컬럼(varchar 100)보다 좁다 — 일부러 그렇다.
 *
 * 컬럼 폭은 저장 한계일 뿐이고, 화면에서 받아야 할 길이는 그보다 훨씬 짧다.
 * 서버 DTO(SignUpRequest.name, UserUpdateRequest.name)도 같은 값을 쓴다.
 */
export const NAME_MAX_LENGTH = 20;

/**
 * 제출 시점에만 검사한다.
 *
 * 이메일 칸(sanitizeEmailInput)처럼 **입력 시점에 지우면 안 된다.** 조합 중인 낱자가
 * 규칙 위반이라 찍는 족족 지워져 한글을 아예 입력할 수 없게 된다.
 * 조용히 받아두었다가 제출할 때 한 번 본다.
 *
 * 서버가 앞뒤 공백을 먼저 잘라내므로(strip_whitespace=True) 여기서도 trim 후에 본다.
 * 안 그러면 프론트만 거부하고 서버는 받아주는, 화면과 API 의 규칙이 어긋나는 상태가 된다.
 */
export function validateName(value: string): string | null {
  const name = value.trim();
  if (name.length < NAME_MIN_LENGTH) return '이름을 두 글자 이상 입력해 주세요.';
  if (!NAME_PATTERN.test(name)) return '이름은 한글과 영문만 입력할 수 있어요.';
  return null;
}
