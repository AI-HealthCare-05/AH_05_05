import { ArrowLeft } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  getCustomChallengeParticipation,
  type CustomChallengeMealSlot,
  type CustomChallengeParticipation,
} from '@/entities/custom-challenge';
import { ApiError } from '@/shared/api/client';
import { Button } from '@/shared/ui';

function positiveId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

function dateLabel(value: string) {
  const [year, month, day] = value.slice(0, 10).split('-');
  return `${year}.${month}.${day}`;
}

function slotLabel(slot: CustomChallengeMealSlot) {
  return { MORNING: '아침', LUNCH: '점심', EVENING: '저녁', BEDTIME: '자기전' }[slot];
}

function progressValue(value: number | string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(100, Math.max(0, parsed)) : 0;
}

function statusLabel(status: CustomChallengeParticipation['status']) {
  if (status === 'ACTIVE') return '진행 중';
  if (status === 'COMPLETED') return '달성';
  if (status === 'CANCELLED') return '취소';
  return '종료';
}

export function CustomChallengeParticipationPage() {
  const { participationId } = useParams();
  const id = positiveId(participationId);
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const generationRef = useRef(0);
  const [participation, setParticipation] = useState<CustomChallengeParticipation | null>(null);
  const [notFound, setNotFound] = useState(id === null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  principalRef.current = principalKey;

  useEffect(() => {
    if (id === null) return;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const requestPrincipal = principalKey;
    setParticipation(null);
    setNotFound(false);
    setError(null);
    getCustomChallengeParticipation(id)
      .then(result => {
        if (generationRef.current === generation && principalRef.current === requestPrincipal) setParticipation(result);
      })
      .catch((reason: unknown) => {
        if (generationRef.current !== generation || principalRef.current !== requestPrincipal) return;
        if (reason instanceof ApiError && reason.status === 401) return;
        if (reason instanceof ApiError && reason.status === 404) setNotFound(true);
        else setError(reason instanceof Error ? reason.message : '맞춤 챌린지를 불러오지 못했어요.');
      });
    return () => {
      if (generationRef.current === generation) generationRef.current += 1;
    };
  }, [id, principalKey, reloadKey]);

  if (notFound) {
    return <main className="flex flex-col gap-4 px-page-x py-5"><h1 className="text-xl font-bold">참여 기록을 찾을 수 없어요</h1><Button variant="secondary" onClick={() => navigate('/challenges')}>챌린지로 돌아가기</Button></main>;
  }
  if (error) {
    return <main className="flex flex-col gap-4 px-page-x py-5"><h1 className="text-xl font-bold">참여 기록을 불러오지 못했어요</h1><p role="alert" className="text-sm text-muted-foreground">{error}</p><Button variant="secondary" onClick={() => setReloadKey(value => value + 1)}>다시 불러오기</Button></main>;
  }
  if (!participation) {
    return <main role="status" aria-label="맞춤 챌린지 참여 기록 불러오는 중" className="mx-page-x my-5 min-h-72 animate-pulse rounded-card bg-muted-bg" />;
  }

  const rate = progressValue(participation.progressRate);
  const targetNames = new Map(participation.targets.map(target => [target.id, target.name]));
  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <header className="flex items-center gap-3">
        <button type="button" aria-label="뒤로 가기" onClick={() => navigate('/challenges')} className="flex size-11 shrink-0 items-center justify-center rounded-pill"><ArrowLeft aria-hidden className="size-5" /></button>
        <div className="min-w-0"><h1 className="break-words text-[22px] font-bold leading-7">{participation.challengeName}</h1><p className="text-caption text-muted-foreground">{statusLabel(participation.status)}</p></div>
      </header>

      <section className="flex flex-col gap-3 rounded-card bg-primary-bg p-5" aria-labelledby="custom-progress-title">
        <div className="flex items-center justify-between gap-3"><h2 id="custom-progress-title" className="text-base font-bold">내 진행률</h2><strong className="text-primary">{String(participation.progressRate)}%</strong></div>
        <div role="progressbar" aria-label="맞춤 챌린지 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={rate} className="h-2 overflow-hidden rounded-pill bg-border"><div className="h-full rounded-pill bg-primary" style={{ width: `${rate}%` }} /></div>
        <p className="text-sm text-foreground">{participation.completedCount} / {participation.targetCount}회</p>
        <p className="text-caption text-muted-foreground">{dateLabel(participation.joinedAt)} ~ {dateLabel(participation.actualEndDate)}</p>
      </section>

      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="custom-target-title">
        <h2 id="custom-target-title" className="text-base font-bold">참여 대상</h2>
        {participation.targets.map(target => <p key={target.id} className="text-sm text-foreground">{target.name}</p>)}
      </section>

      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="custom-record-title">
        <h2 id="custom-record-title" className="text-base font-bold">자동 반영 기록</h2>
        {participation.occurrences.length === 0 ? <p className="text-sm text-muted-foreground">반영된 기록이 아직 없어요.</p> : participation.occurrences.map(occurrence => (
          <p key={occurrence.id} className="text-sm text-muted-foreground">
            {dateLabel(occurrence.scheduledDate)} · {slotLabel(occurrence.slot)} · {occurrence.isCompleted ? '완료' : '예정'} · {targetNames.get(occurrence.targetId) ?? '참여 대상'}
          </p>
        ))}
      </section>

      <p className="text-caption leading-5 text-muted-foreground">진행률은 홈과 복약 기록을 기준으로 자동 계산돼요.</p>
      <Button variant="secondary" onClick={() => setReloadKey(value => value + 1)}>최신 진행률 불러오기</Button>
    </main>
  );
}
