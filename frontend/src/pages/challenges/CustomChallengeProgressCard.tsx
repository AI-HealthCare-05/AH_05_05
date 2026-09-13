import { Link } from 'react-router';
import { customChallengeDayProgress, type CustomChallengeParticipation } from '@/entities/custom-challenge';
import { ChallengeTypeBadge } from './ChallengeTypeBadge';

function statusLabel(status: CustomChallengeParticipation['status']) {
  if (status === 'ACTIVE') return '진행 중';
  if (status === 'COMPLETED') return '달성';
  if (status === 'CANCELLED') return '취소';
  return '종료';
}

export function CustomChallengeProgressCard({ participation: item }: { participation: CustomChallengeParticipation }) {
  const days = customChallengeDayProgress(item);
  const parsed = days.rate;
  const rate = Number.isFinite(parsed) ? Math.min(100, Math.max(0, parsed)) : 0;
  return (
    <article aria-label={item.challengeName} className="relative flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <ChallengeTypeBadge official={false} />
          <Link to={`/challenges/custom-participations/${item.id}`} aria-label={`${item.challengeName} 자세히 보기`} className="block break-words text-base font-bold text-foreground after:absolute after:inset-0 after:rounded-card focus-visible:after:outline-2 focus-visible:after:outline-primary [overflow-wrap:anywhere]">{item.challengeName}</Link>
        </div>
        {item.status !== 'ACTIVE' && <span className="shrink-0 rounded-pill bg-muted-bg px-2 py-1 text-micro font-bold text-muted-foreground">{statusLabel(item.status)}</span>}
      </div>
      <p className="break-words text-caption text-muted-foreground [overflow-wrap:anywhere]">{item.targets.map(target => target.name).join(' · ')}</p>
      <div className="flex items-center justify-between gap-2 text-caption text-muted-foreground"><span>{days.completed} / {days.target}일</span><span className="font-bold text-primary">{rate}% 달성</span></div>
      <div role="progressbar" aria-label={`${item.challengeName} 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={rate} className="h-2 overflow-hidden rounded-pill bg-border"><div className="h-full rounded-pill bg-primary" style={{ width: `${rate}%` }} /></div>
    </article>
  );
}
