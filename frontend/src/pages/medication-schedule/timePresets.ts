/**
 * 시간 선택 시트(`09-A`)가 쓰는 값들.
 *
 * 통합 슬롯 재설계로 약별 시각이 없어지면서 `defaultTimesFor`·`formatSlotLabel`은
 * 삭제했습니다. 시간대별 기본 시각은 `slotAssignment.ts`의 DEFAULT_MEAL_TIMES입니다.
 */
export interface TimePreset {
  label: string;
  time: string;
}

/**
 * 시트 상단 프리셋 칩.
 *
 * DEFAULT_MEAL_TIMES 와 같은 값·같은 이름을 유지하세요. 이전에는 "저녁 20:00 / 자기 전"
 * 이었는데, 통합 슬롯의 저녁이 19:00 이고 이름도 "취침 전"이라 한 앱에서 저녁이 두 값으로
 * 보이는 문제가 있었습니다. 값을 맞춰 두 곳이 어긋나지 않게 합니다.
 */
export const TIME_PRESETS: TimePreset[] = [
  { label: '아침약', time: '08:00' },
  { label: '점심약', time: '13:00' },
  { label: '저녁약', time: '19:00' },
  { label: '취침약', time: '22:00' },
];

/** 시각은 30분 단위(분은 00 또는 30)만 허용합니다. */
export const MINUTE_OPTIONS = ['00', '30'];

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));
