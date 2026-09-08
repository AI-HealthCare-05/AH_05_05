import type { ChallengeProgressPeriod } from '@/entities/challenge';

const koreaDateFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

export function inclusiveChallengeEndDate(exclusiveEndAt: string): string {
  const timestamp = Date.parse(exclusiveEndAt);
  if (!Number.isFinite(timestamp)) return exclusiveEndAt.slice(0, 10);
  const parts = koreaDateFormatter.formatToParts(new Date(timestamp - 1));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(item => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function datesBetween(start: string, end: string): string[] {
  const dates: string[] = [];
  const current = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  while (current <= last && dates.length < 366) {
    dates.push(current.toISOString().slice(0, 10));
    current.setUTCDate(current.getUTCDate() + 1);
  }
  return dates;
}

export function challengeVerificationDates(periods: ChallengeProgressPeriod[]): string[] {
  return [...new Set(periods.flatMap(period => datesBetween(period.period_start, period.period_end)))];
}

export function trailingNonVerificationDays(
  periods: ChallengeProgressPeriod[],
  inclusiveEndDate: string,
): number {
  const finalPeriodEnd = periods.at(-1)?.period_end;
  if (!finalPeriodEnd) return 0;
  const gap = Math.round(
    (Date.parse(`${inclusiveEndDate}T00:00:00Z`) - Date.parse(`${finalPeriodEnd}T00:00:00Z`)) /
      86_400_000,
  );
  return Number.isFinite(gap) ? Math.max(0, gap) : 0;
}
