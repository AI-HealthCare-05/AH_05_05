/**
 * 시간 선택 시트(`09-A`)가 쓰는 값들.
 *
 * 시간대별 기본 시각은 `shared/model/mealSlot.ts`의 DEFAULT_MEAL_TIMES입니다.
 */
/** 시각은 30분 단위(분은 00 또는 30)만 허용합니다. */
export const MINUTE_OPTIONS = ['00', '30'];

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));
