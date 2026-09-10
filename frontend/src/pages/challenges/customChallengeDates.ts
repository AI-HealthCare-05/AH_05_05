const SEOUL_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
});

export function seoulDate(value = new Date()) {
  const parts = new Map(SEOUL_DATE.formatToParts(value).map(part => [part.type, part.value]));
  return `${parts.get('year')}-${parts.get('month')}-${parts.get('day')}`;
}

export function customChallengeDateLabel(value: string) {
  const date = value.includes('T') ? seoulDate(new Date(value)) : value;
  return date.replaceAll('-', '.');
}
