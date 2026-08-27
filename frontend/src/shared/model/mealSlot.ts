export type MealSlot = 'morning' | 'lunch' | 'evening' | 'bedtime';

export const DEFAULT_MEAL_TIMES = {
  morning: '08:00',
  lunch: '13:00',
  evening: '19:00',
  bedtime: '22:00',
} as const;

/**
 * label — 시간대 카드·복약 설정처럼 "약 묶음"을 나타낼 때 씁니다.
 * short — 좁은 칩·목록·그리드처럼 시간대만 짧게 나타낼 때 씁니다.
 */
const MEAL_SLOT_LABELS: Record<MealSlot, { label: string; short: string }> = {
  morning: { label: '아침약', short: '아침' },
  lunch: { label: '점심약', short: '점심' },
  evening: { label: '저녁약', short: '저녁' },
  bedtime: { label: '취침약', short: '취침' },
};

export const SLOT_ORDER: MealSlot[] = ['morning', 'lunch', 'evening', 'bedtime'];

export const MEAL_SLOTS: ReadonlyArray<{
  value: MealSlot;
  label: string;
  short: string;
}> = SLOT_ORDER.map((value) => ({ value, ...MEAL_SLOT_LABELS[value] }));

export function mealSlotLabel(slot: MealSlot, variant: 'label' | 'short' = 'short'): string {
  return MEAL_SLOT_LABELS[slot][variant];
}

function slotsFromTiming(timing: string): MealSlot[] {
  const found = new Set<MealSlot>();
  if (/아침|조식|기상/.test(timing)) found.add('morning');
  if (/점심|중식/.test(timing)) found.add('lunch');
  if (/저녁|석식/.test(timing)) found.add('evening');
  if (/취침|자기\s?전|잠자기\s?전|수면\s?전|자기전/.test(timing)) found.add('bedtime');
  return SLOT_ORDER.filter((slot) => found.has(slot));
}

export function needsSlotConfirmation(timesPerDay: number | null, timing: string): boolean {
  if (timesPerDay === null) return false;
  return slotsFromTiming(timing).length !== timesPerDay;
}

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

export function exceedsSlotCapacity(timesPerDay: number | null): boolean {
  return timesPerDay !== null && timesPerDay > 4;
}

export function isMealTimeOrderValid(times: Record<MealSlot, string>): boolean {
  for (let index = 1; index < SLOT_ORDER.length; index += 1) {
    if (times[SLOT_ORDER[index]] <= times[SLOT_ORDER[index - 1]]) return false;
  }
  return true;
}
