import { Link } from 'react-router';

import { Button } from '@/shared/ui/Button';
import type { ChallengeParticipation } from '@/features/challenges';

interface ChallengeProgressCardProps {
  participation: ChallengeParticipation;
  href: string;
  onCheckIn?: () => void;
  checkInDisabled?: boolean;
  unitLabel?: string;
}

const kindLabel: Record<ChallengeParticipation['kind'], string> = {
  official: '공식 배지',
  medication: '자동 연동',
  supplement: '자동 연동',
  review: '기록 확인',
  visit: '일정 확인',
  personal: '나만의 챌린지',
};

export function ChallengeProgressCard({
  participation,
  href,
  onCheckIn,
  checkInDisabled = false,
  unitLabel,
}: ChallengeProgressCardProps) {
  const directCheck =
    participation.status === 'active' &&
    (participation.kind === 'official' || participation.kind === 'personal');

  return (
    <article
      aria-label={participation.title}
      className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card"
    >
      <div className="flex items-start justify-between gap-3">
        <Link
          to={href}
          aria-label={`${participation.title} 자세히 보기`}
          className="min-w-0 flex-1 text-base font-bold text-foreground"
        >
          {participation.title}
        </Link>
        <span className="shrink-0 rounded-pill bg-primary-bg px-2 py-1 text-micro font-bold text-primary">
          {participation.status === 'achieved' ? '달성' : participation.status === 'missed' ? '종료' : kindLabel[participation.kind]}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 text-caption text-muted-foreground">
        <span>{participation.startDate.slice(5).replace('-', '.')} ~ {participation.endDate.slice(5).replace('-', '.')}</span>
        <span className="font-bold text-primary">{participation.percent}% 달성</span>
      </div>
      <div
        role="progressbar"
        aria-label={`${participation.title} 진행률`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={participation.percent}
        className="h-2 overflow-hidden rounded-pill bg-border"
      >
        <div
          className="h-full rounded-pill bg-primary transition-[width] motion-reduce:transition-none"
          style={{ width: `${Math.min(100, Math.max(0, participation.percent))}%` }}
        />
      </div>
      <p className="text-caption text-foreground">
        {participation.completed} / {participation.target}{unitLabel ?? (
          participation.kind === 'medication' || participation.kind === 'supplement'
            ? '회 완료'
            : participation.kind === 'review' || participation.kind === 'visit'
              ? '개 확인'
              : '일 인증'
        )}
      </p>
      {directCheck ? (
        <Button
          onClick={onCheckIn}
          disabled={participation.todayCompleted || checkInDisabled}
          className="h-11 min-h-11"
        >
          {checkInDisabled ? '시작 전이에요' : participation.todayCompleted ? '오늘 인증 완료' : '했어요'}
        </Button>
      ) : null}
    </article>
  );
}
