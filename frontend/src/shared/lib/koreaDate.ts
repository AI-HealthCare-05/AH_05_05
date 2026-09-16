/** Backend save_dose accepts today and the preceding 365 calendar days. */
export const MAX_DOSE_HISTORY_DAYS = 366;

export function todayInKorea(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(now);
}

function shiftISODate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function earliestDoseDateInKorea(now: Date = new Date()): string {
  return shiftISODate(todayInKorea(now), -(MAX_DOSE_HISTORY_DAYS - 1));
}

function isValidISODate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function isDoseDateInRange(value: string, now: Date = new Date()): boolean {
  if (!isValidISODate(value)) return false;
  const today = todayInKorea(now);
  return value >= earliestDoseDateInKorea(now) && value <= today;
}

export function doseDateValidationMessage(
  value: string,
  now: Date = new Date(),
): string | null {
  const today = todayInKorea(now);
  if (!isValidISODate(value)) return '첫 복용 날짜를 입력해주세요.';
  if (value > today) return '첫 복용 날짜는 오늘을 넘을 수 없어요.';
  if (value < earliestDoseDateInKorea(now)) {
    return '첫 복용 날짜는 오늘 기준 최근 365일 이내로 골라주세요.';
  }
  return null;
}
