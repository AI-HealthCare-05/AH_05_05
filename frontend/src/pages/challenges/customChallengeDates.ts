const SEOUL_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
});

export function seoulDate(value = new Date()) {
  const parts = new Map(SEOUL_DATE.formatToParts(value).map(part => [part.type, part.value]));
  return `${parts.get('year')}-${parts.get('month')}-${parts.get('day')}`;
}

export function customChallengeDateLabel(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.replaceAll('-', '.');
  if (!value.includes('T')) return value;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? seoulDate(new Date(timestamp)).replaceAll('-', '.') : value;
}
