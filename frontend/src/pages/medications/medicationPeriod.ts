import type { MedicationOverviewRange } from '@/entities/medication';

export type MedicationPeriodPreset = 'three-months' | 'six-months' | 'one-year' | 'custom';

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

export function addCalendarYears(value: string, years: number): string {
  const [year, month, day] = value.split('-').map(Number);
  const target = new Date(year + years, month - 1, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(day, lastDay));
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
  preset: Exclude<MedicationPeriodPreset, 'custom'>,
  today: Date,
): Required<MedicationOverviewRange> {
  const months = preset === 'three-months' ? 3 : preset === 'six-months' ? 6 : 12;
  return {
    from: subtractCalendarMonths(today, months),
    to: localIsoDate(today),
  };
}

export function presetForRange(
  range: MedicationOverviewRange,
  today: Date,
): MedicationPeriodPreset {
  if (!range.from && !range.to) return 'six-months';
  if (range.from && range.to) {
    for (const preset of ['three-months', 'six-months', 'one-year'] as const) {
      const candidate = presetRange(preset, today);
      if (candidate.from === range.from && candidate.to === range.to) return preset;
    }
  }
  return 'custom';
}

export function medicationPeriodLabel(range: MedicationOverviewRange, today: Date): string {
  const preset = presetForRange(range, today);
  if (preset === 'three-months') return '최근 3개월';
  if (preset === 'six-months') return '최근 6개월';
  if (preset === 'one-year') return '최근 1년';
  return '직접 지정';
}
