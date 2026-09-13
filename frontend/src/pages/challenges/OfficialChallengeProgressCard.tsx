import { Link } from 'react-router';

import type { ChallengeParticipation } from '@/entities/challenge';
import { Button } from '@/shared/ui/Button';
import { inclusiveChallengeEndDate } from './officialChallengeDates';
import { officialChallengeProgress } from './officialChallengeProgress';
import { ChallengeTypeBadge } from './ChallengeTypeBadge';

function statusLabel(participation: ChallengeParticipation) {
  if (participation.status === 'COMPLETED') return '달성';
  if (participation.status === 'CANCELLED') return '취소';
  if (participation.status === 'EXPIRED') return '종료';
  if (participation.challenge.check_type_code !== 'SELF') return '관리자 확인';
  return participation.challenge.reward_badge ? '공식 배지' : '직접 인증';
}

function checkInLabel(participation: ChallengeParticipation, pending: boolean) {
  if (pending) return '인증 기록 중';
  if (participation.today_verification?.status === 'APPROVED') return '오늘 인증 완료';
  if (participation.today_verification?.status === 'PENDING') return '인증 확인 중';
  if (participation.today_verification?.status === 'REJECTED') return '인증이 반려됐어요';
  if (!participation.can_verify) return '오늘은 인증할 수 없어요';
  return '했어요';
}

export function OfficialChallengeProgressCard({
  participation,
  pending,
  error,
  refreshRequired = false,
  onCheckIn,
  onRefresh,
}: {
  participation: ChallengeParticipation;
  pending: boolean;
  error?: string;
  refreshRequired?: boolean;
  onCheckIn: () => void;
  onRefresh?: () => void;
}) {
  const { rate, label: progressLabel } = officialChallengeProgress(participation);
  const isSelfActive = participation.status === 'ACTIVE' && participation.challenge.check_type_code === 'SELF';
  const label = checkInLabel(participation, pending);

  return (
    <article aria-label={participation.challenge_name} className="relative flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <ChallengeTypeBadge official />
          <Link to={`/challenges/participations/${participation.id}`} aria-label={`${participation.challenge_name} 자세히 보기`} className="block break-words text-base font-bold text-foreground after:absolute after:inset-0 after:rounded-card focus-visible:after:outline-2 focus-visible:after:outline-primary [overflow-wrap:anywhere]">
            {participation.challenge_name}
          </Link>
        </div>
        {participation.status !== 'ACTIVE' && <span className="shrink-0 rounded-pill bg-muted-bg px-2 py-1 text-micro font-bold text-muted-foreground">{statusLabel(participation)}</span>}
      </div>
      {refreshRequired ? (
        <div role="status" className="flex flex-col gap-2 rounded-input bg-muted-bg p-3">
          <p className="text-caption text-muted-foreground">최신 진행 정보 확인 필요</p>
          <Button variant="secondary" onClick={onRefresh} disabled={pending} className="relative z-10 h-11 min-h-11">다시 불러오기</Button>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2 text-caption text-muted-foreground">
            <span>{participation.started_at.slice(0, 10).slice(5).replace('-', '.')} ~ {inclusiveChallengeEndDate(participation.end_at).slice(5).replace('-', '.')}</span>
            <span className="font-bold text-primary">{rate}% 달성</span>
          </div>
          <div role="progressbar" aria-label={`${participation.challenge_name} 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={rate} className="h-2 overflow-hidden rounded-pill bg-border">
            <div className="h-full rounded-pill bg-primary transition-[width] motion-reduce:transition-none" style={{ width: `${rate}%` }} />
          </div>
          <p className="text-caption text-foreground">{progressLabel} 인증</p>
        </>
      )}
      {participation.challenge.check_type_code === 'MANUAL' ? (
        <p className="rounded-input bg-muted-bg p-3 text-caption text-muted-foreground">관리자 확인 방식 · 앱 인증은 지원하지 않아요.</p>
      ) : null}
      {error ? <p role="alert" className="text-caption text-danger-strong">{error}</p> : null}
      {isSelfActive ? (
        <Button onClick={onCheckIn} disabled={pending || !participation.can_verify} className="relative z-10 h-11 min-h-11">{label}</Button>
      ) : null}
    </article>
  );
}
