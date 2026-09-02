export interface DateLabelOptions {
  includeYear?: boolean;
}

function dateParts(value: string): [number, number, number] | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

export function formatDateLabel(value: string, options: DateLabelOptions = {}): string {
  const parts = dateParts(value);
  if (!parts) return value;
  const [year, month, day] = parts;
  return options.includeYear ? `${year}년 ${month}월 ${day}일` : `${month}월 ${day}일`;
}

export function formatDatePeriod(
  from: string,
  to: string,
  options: DateLabelOptions = {},
): string {
  const start = dateParts(from);
  const end = dateParts(to);
  if (!start || !end) return from && to ? `${from} ~ ${to}` : '';
  const [fromYear, fromMonth, fromDay] = start;
  const [toYear, toMonth, toDay] = end;
  if (options.includeYear && fromYear !== toYear) {
    return `${fromYear}년 ${fromMonth}월 ${fromDay}일 ~ ${toYear}년 ${toMonth}월 ${toDay}일`;
  }
  const prefix = options.includeYear ? `${fromYear}년 ` : '';
  return fromMonth === toMonth
    ? `${prefix}${fromMonth}월 ${fromDay}일 ~ ${toDay}일`
    : `${prefix}${fromMonth}월 ${fromDay}일 ~ ${toMonth}월 ${toDay}일`;
}
