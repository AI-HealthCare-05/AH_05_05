export type MinuteStep = 1 | 10 | 30;

/** 기존 00·30분 선택은 보존하되 비활성화합니다.
 * 복원 시 서버 medication_schedule.py의 같은 설정도 함께 true로 바꾸세요.
 */
export const USE_HALF_HOUR_REMINDERS = false;
export const REMINDER_MINUTE_STEP: MinuteStep = USE_HALF_HOUR_REMINDERS ? 30 : 1;
export const MINUTE_OPTIONS = getMinuteOptions(REMINDER_MINUTE_STEP);

export function getMinuteOptions(step: MinuteStep): string[] {
  return Array.from({ length: 60 / step }, (_, index) =>
    String(index * step).padStart(2, '0'),
  );
}

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) =>
  String(hour).padStart(2, '0'),
);
