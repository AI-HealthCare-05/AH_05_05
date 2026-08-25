export const MIN_BIRTH_DATE = '1900-01-01';

export const UNDER_FOURTEEN_MESSAGE = '만 14세 미만은 보호자와 함께 가입해주세요.';

export function formatDateInputValue(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function validateBirthDate(value: string, today = new Date()): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return '생년월일을 입력해주세요.';

  const todayValue = formatDateInputValue(today);
  if (value < MIN_BIRTH_DATE) return '1900년 1월 1일 이후의 날짜를 입력해주세요.';
  if (value > todayValue) return '미래 날짜는 입력할 수 없어요.';

  const [year, month, day] = value.split('-').map(Number);
  const birthDate = new Date(year, month - 1, day);
  if (
    birthDate.getFullYear() !== year ||
    birthDate.getMonth() !== month - 1 ||
    birthDate.getDate() !== day
  ) {
    return '올바른 생년월일을 입력해주세요.';
  }

  const age = calculateFullAge(value, today);
  return age < 14 ? UNDER_FOURTEEN_MESSAGE : null;
}

export function calculateFullAge(birthDate: string, today = new Date()): number {
  const [birthYear, birthMonth, birthDay] = birthDate.split('-').map(Number);
  let age = today.getFullYear() - birthYear;
  const birthdayNotReached =
    today.getMonth() + 1 < birthMonth ||
    (today.getMonth() + 1 === birthMonth && today.getDate() < birthDay);
  if (birthdayNotReached) age -= 1;
  return age;
}
