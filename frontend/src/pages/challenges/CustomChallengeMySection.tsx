import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  getCustomChallengeParticipations,
  type CustomChallengeParticipation,
} from '@/entities/custom-challenge';
import { ApiError } from '@/shared/api/client';
import { Button } from '@/shared/ui';

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

export function CustomChallengeMySection() {
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const generationRef = useRef(0);
  const [items, setItems] = useState<CustomChallengeParticipation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  principalRef.current = principalKey;

  useEffect(() => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const requestPrincipal = principalKey;
    setItems(null);
    setError(null);
    getCustomChallengeParticipations()
      .then(result => {
        if (generationRef.current === generation && principalRef.current === requestPrincipal) setItems(result.items);
      })
      .catch((reason: unknown) => {
        if (generationRef.current !== generation || principalRef.current !== requestPrincipal) return;
        if (reason instanceof ApiError && reason.status === 401) return;
        setError(reason instanceof Error ? reason.message : '맞춤 챌린지를 불러오지 못했어요.');
      });
    return () => {
      if (generationRef.current === generation) generationRef.current += 1;
    };
  }, [principalKey, reloadKey]);

  return (
    <section role="region" aria-labelledby="custom-challenges-title" className="flex flex-col gap-3">
      <div className="flex min-h-touch items-center justify-between gap-3">
        <h2 id="custom-challenges-title" className="text-base font-bold">맞춤 챌린지</h2>
        <Link to="/challenges/tailored" className="py-3 text-sm font-bold text-primary">새로 참여하기 ›</Link>
      </div>
      {items === null && !error ? <div role="status" aria-label="내 맞춤 챌린지 불러오는 중" className="min-h-28 animate-pulse rounded-card bg-muted-bg" /> : null}
      {error ? (
        <div role="alert" className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button variant="secondary" onClick={() => setReloadKey(value => value + 1)}>다시 불러오기</Button>
        </div>
      ) : null}
      {items?.length === 0 ? (
        <div className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">참여한 맞춤 챌린지가 없어요.</p>
          <Link to="/challenges/tailored" className="text-sm font-bold text-primary">내 기록으로 시작하기 ›</Link>
        </div>
      ) : null}
      {items?.map(item => {
        const rate = progressValue(item.progressRate);
        return (
          <article key={item.id} aria-label={item.challengeName} className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
            <div className="flex items-start justify-between gap-3">
              <Link to={`/challenges/custom-participations/${item.id}`} aria-label={`${item.challengeName} 자세히 보기`} className="min-w-0 flex-1 text-base font-bold text-foreground">{item.challengeName}</Link>
              <span className="shrink-0 rounded-pill bg-primary-bg px-2 py-1 text-micro font-bold text-primary">{statusLabel(item.status)}</span>
            </div>
            <div className="flex items-center justify-between gap-2 text-caption text-muted-foreground"><span>{item.completedCount} / {item.targetCount}회</span><span className="font-bold text-primary">{String(item.progressRate)}% 달성</span></div>
            <div role="progressbar" aria-label={`${item.challengeName} 진행률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={rate} className="h-2 overflow-hidden rounded-pill bg-border"><div className="h-full rounded-pill bg-primary" style={{ width: `${rate}%` }} /></div>
          </article>
        );
      })}
    </section>
  );
}
