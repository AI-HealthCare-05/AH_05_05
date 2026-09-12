export function ChallengeTypeBadge({ official }: { official: boolean }) {
  return <span className={`inline-block self-start shrink-0 rounded-pill px-2 py-1 text-micro font-bold ${official ? 'bg-primary-bg text-primary' : 'bg-warning-bg text-warning-strong'}`}>
    {official ? '공식' : '맞춤'}
  </span>;
}
