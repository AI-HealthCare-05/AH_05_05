import type { MedicationOverviewRange } from '@/entities/medication';

export type MedicationPeriodPreset = 'one-month' | 'three-months' | 'six-months' | 'custom';

export function localIsoDate(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

export function subtractCalendarMonths(today: Date, months: number): string {
  const target = new Date(today.getFullYear(), today.getMonth() - months, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(today.getDate(), lastDay));
  return localIsoDate(target);
}

export function medicationRangeFromSearchParams(params: URLSearchParams): MedicationOverviewRange {
  const from = params.get('from');
  const to = params.get('to');
  return {
    ...(from ? { from } : {}),
    ...(to ? { to } : {}),
  };
}

export function presetRange(
  preset: Exclude<MedicationPeriodPreset, 'three-months' | 'custom'>,
  today: Date,
): Required<MedicationOverviewRange> {
  return {
    from: subtractCalendarMonths(today, preset === 'one-month' ? 1 : 6),
    to: localIsoDate(today),
  };
}

export function presetForRange(
  range: MedicationOverviewRange,
  today: Date,
): MedicationPeriodPreset {
  if (!range.from && !range.to) return 'three-months';
  if (range.from && range.to) {
    for (const preset of ['one-month', 'six-months'] as const) {
      const candidate = presetRange(preset, today);
      if (candidate.from === range.from && candidate.to === range.to) return preset;
    }
  }
  return 'custom';
}

export function medicationPeriodLabel(range: MedicationOverviewRange, today: Date): string {
  const preset = presetForRange(range, today);
  if (preset === 'one-month') return '최근 1개월';
  if (preset === 'three-months') return '최근 3개월';
  if (preset === 'six-months') return '최근 6개월';
  return '직접 지정';
}
