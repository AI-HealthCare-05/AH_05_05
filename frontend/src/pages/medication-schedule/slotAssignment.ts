import type { MealSlot } from '@/entities/medication';

export const DEFAULT_MEAL_TIMES = {
  morning: '08:00',
  lunch: '13:00',
  evening: '19:00',
  bedtime: '22:00',
} as const;

/**
 * label   — 시간대 카드·시작 시점에 쓰는 이름. 약 봉투 표기와 같은 "아침약" 형태로,
 *           시각이 아니라 "그 시간에 먹는 약 묶음"이라는 걸 드러냅니다.
 * short   — 약별 토글 버튼에 쓰는 이름. 375px에 4개가 들어가야 해서 짧게 씁니다.
 *
 * 라벨을 두 벌 두는 이유는 폭 때문입니다. 한 곳에서만 정의해 매핑 실수를 막습니다.
 */
export const MEAL_SLOTS: Array<{ value: MealSlot; label: string; short: string }> = [
  { value: 'morning', label: '아침약', short: '아침' },
  { value: 'lunch', label: '점심약', short: '점심' },
  { value: 'evening', label: '저녁약', short: '저녁' },
  { value: 'bedtime', label: '취침약', short: '취침' },
];

/** 시각 순서 검증에 쓰는 순서. MEAL_SLOTS 와 같은 순서를 유지하세요. */
export const SLOT_ORDER: MealSlot[] = ['morning', 'lunch', 'evening', 'bedtime'];

/**
 * timing 문구에서 시간대를 읽습니다. "아침·저녁 식후" → ['morning', 'evening']
 * OCR 원문에 영문·약어가 섞여 올 수 있어 한글 키워드만 봅니다(추측해서 틀리는 것보다
 * 못 찾고 폴백하는 게 안전합니다).
 *
 * 반환 순서는 SLOT_ORDER 를 따릅니다 — 문구에 "취침 전, 아침"처럼 뒤집혀 와도
 * 화면 표시 순서가 흔들리지 않게 합니다.
 */
function slotsFromTiming(timing: string): MealSlot[] {
  const found = new Set<MealSlot>();
  if (/아침|조식|기상/.test(timing)) found.add('morning');
  if (/점심|중식/.test(timing)) found.add('lunch');
  if (/저녁|석식/.test(timing)) found.add('evening');
  if (/취침|자기\s?전|잠자기\s?전|수면\s?전|자기전/.test(timing)) found.add('bedtime');
  return SLOT_ORDER.filter((slot) => found.has(slot));
}

/**
 * 자동 배정. 문구에서 읽은 시간대 개수가 복용 횟수와 정확히 맞을 때만 그것을 쓰고,
 * 아니면 횟수 기준 기본값으로 떨어집니다.
 *
 * 1회 → 아침
 * 2회 → 아침·저녁
 * 3회 → 아침·점심·저녁
 * 4회 → 아침·점심·저녁·취침 전
 * 5회 이상은 슬롯이 4개라 표현할 수 없습니다. 전부 켜고 화면에 경고를 띄웁니다.
 */
export function defaultSlotsFor(timesPerDay: number | null, timing: string): MealSlot[] {
  if (timesPerDay === null) return [];

  const fromTiming = slotsFromTiming(timing);
  if (fromTiming.length === timesPerDay) return fromTiming;

  switch (timesPerDay) {
    case 1:
      return ['morning'];
    case 2:
      return ['morning', 'evening'];
    case 3:
      return ['morning', 'lunch', 'evening'];
    default:
      return ['morning', 'lunch', 'evening', 'bedtime'];
  }
}

/** 1일 5회 이상 — 슬롯 4개로 표현 불가. 화면에 경고를 띄우는 조건. */
export function exceedsSlotCapacity(timesPerDay: number | null): boolean {
  return timesPerDay !== null && timesPerDay > 4;
}

/**
 * 시각이 아침 → 점심 → 저녁 → 취침 전 순으로 늘어나는지 검사합니다.
 * 뒤집히면 알림 순서가 어긋나고 홈의 "오늘의 복약" 정렬도 깨집니다.
 *
 * 취침 전 자정 넘김은 미지원입니다. 분 선택이 00·30뿐이고 시가 23까지라
 * 최대값이 23:30으로 자연히 제한됩니다.
 */
export function isMealTimeOrderValid(times: Record<MealSlot, string>): boolean {
  for (let i = 1; i < SLOT_ORDER.length; i += 1) {
    if (times[SLOT_ORDER[i]] <= times[SLOT_ORDER[i - 1]]) return false;
  }
  return true;
}
