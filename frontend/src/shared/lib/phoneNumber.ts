const MOBILE_PHONE_PATTERN = /^01(?:0|1|[6-9])\d{7,8}$/;

/** formatPhoneNumberInput 이 만들 수 있는 가장 긴 문자열(`010-1234-5678`). */
export const PHONE_NUMBER_MAX_LENGTH = 13;

export function normalizePhoneNumber(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (digits.startsWith('82') && digits.length >= 11) return `0${digits.slice(2)}`;
  return digits;
}

export function formatPhoneNumberInput(value: string): string {
  const digits = normalizePhoneNumber(value).slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  const middleEnd = digits.length === 10 ? 6 : 7;
  return `${digits.slice(0, 3)}-${digits.slice(3, middleEnd)}-${digits.slice(middleEnd)}`;
}

export function validatePhoneNumber(value: string): string | null {
  return MOBILE_PHONE_PATTERN.test(normalizePhoneNumber(value))
    ? null
    : '휴대전화 번호를 확인해 주세요.';
}
