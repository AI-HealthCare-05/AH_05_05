/**
 * REQ-CARE-003의 시간 프리셋과 기본 슬롯 시각.
 *
 * 아침 08:00 · 저녁 20:00은 Figma `09`(125:50)에 그려진 값입니다.
 * 점심 13:00 · 자기 전 22:00은 Figma·요구사항 어디에도 값이 없어 기획 확인 후 정했습니다.
 */
export interface TimePreset {
  label: string;
  time: string;
}

export const TIME_PRESETS: TimePreset[] = [
  { label: '아침', time: '08:00' },
  { label: '점심', time: '13:00' },
  { label: '저녁', time: '20:00' },
  { label: '자기 전', time: '22:00' },
];

/** 시각은 30분 단위(분은 00 또는 30)만 허용합니다 — 스펙 5-3. */
export const MINUTE_OPTIONS = ['00', '30'];

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));

/**
 * 복용 횟수만큼 기본 시각을 만듭니다(REQ-CARE-003 "복용 횟수만큼 시간 슬롯 자동 생성").
 * 1회는 저녁, 2회는 아침·저녁 — Figma `09`의 리바록사반·셀레콕시브와 같습니다.
 */
export function defaultTimesFor(timesPerDay: number): string[] {
  switch (timesPerDay) {
    case 1:
      return ['20:00'];
    case 2:
      return ['08:00', '20:00'];
    case 3:
      return ['08:00', '13:00', '20:00'];
    default:
      return ['08:00', '13:00', '20:00', '22:00'].slice(0, Math.max(timesPerDay, 1));
  }
}

/**
 * 슬롯 버튼에 붙는 라벨. 프리셋과 정확히 일치할 때만 "아침 08:00"처럼 이름을 붙이고,
 * 사용자가 직접 고른 시각은 "08:30"처럼 시각만 보여줍니다.
 * (아침/점심/저녁의 시간대 경계는 요구사항에 없어 임의로 정하지 않았습니다.)
 */
export function formatSlotLabel(time: string): string {
  const preset = TIME_PRESETS.find((p) => p.time === time);
  return preset ? `${preset.label} ${time}` : time;
}
