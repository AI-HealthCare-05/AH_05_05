import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  claimCustomChallengeReward,
  customChallengeDayProgress,
  getCustomChallengeParticipation,
  cancelCustomChallenge,
  invalidateCustomChallengeProgress,
  subscribeCustomChallengeProgressInvalidation,
  type CustomChallengeBadgeAward,
  type CustomChallengeParticipation,
} from '@/entities/custom-challenge';
import { ApiError, getAuthGeneration } from '@/shared/api/client';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { captureBadgeAwardScope, enqueueBadgeAward } from '@/shared/lib/badgeAwards';
import { Button, Header, Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/shared/ui';
import { LoadingState } from '@/shared/ui/LoadingState';
import { CustomChallengeCalendar } from './CustomChallengeCalendar';
import { customChallengeDateLabel as dateLabel } from './customChallengeDates';

function positiveId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
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

function canClaimReward(participation: CustomChallengeParticipation) {
  return participation.status === 'COMPLETED'
    || (participation.status === 'ACTIVE' && participation.occurrences.length > 0
      && participation.occurrences.every(occurrence => occurrence.isCompleted));
}

export function CustomChallengeParticipationPage() {
  const { participationId } = useParams();
  const id = positiveId(participationId);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const generationRef = useRef(0);
  const readGenerationRef = useRef(0);
  const refreshRef = useRef<() => void>(() => {});
  const refreshAfterCancelRef = useRef(false);
  const [participation, setParticipation] = useState<CustomChallengeParticipation | null>(null);
  const [notFound, setNotFound] = useState(id === null);
  const [error, setError] = useState<string | null>(null);
  const [award, setAward] = useState<CustomChallengeBadgeAward | null>(null);
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claimPending, setClaimPending] = useState(false);
  const claimPendingRef = useRef(false);
  const retryClaimRef = useRef<() => void>(() => {});
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelPending, setCancelPending] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const cancelPendingRef = useRef(false);
  principalRef.current = principalKey;

  function handleBack() {
    const index = window.history.state?.idx;
    if (typeof index === 'number' && index > 0) {
      navigate(-1);
      return;
    }
    navigate('/challenges', { replace: true });
  }

  useEffect(() => {
    const generation = ++generationRef.current;
    let active = true;
    let pending = false;
    let invalidatedGeneration: number | null = null;
    let hasData = false;
    let claimAttempted = false;
    let claimSettled = false;
    setCancelOpen(false);
    setCancelPending(false);
    setCancelError(null);
    cancelPendingRef.current = false;
    refreshAfterCancelRef.current = false;
    setParticipation(null);
    setNotFound(id === null);
    setError(null);
    setAward(null);
    setClaimError(null);
    setClaimPending(false);
    claimPendingRef.current = false;
    retryClaimRef.current = () => {};
    if (id === null) {
      refreshRef.current = () => {};
      return;
    }
    const requestId = id;
    const requestPrincipal = principalKey;
    const isIdentityCurrent = () => active && generationRef.current === generation
      && principalRef.current === requestPrincipal
      // Browser history updates before React commits navigation and runs this effect's cleanup.
      && window.location.pathname === pathname;

    function refresh(invalidatePending = false) {
      if (!isIdentityCurrent()) return;
      if (cancelPendingRef.current) {
        refreshAfterCancelRef.current = true;
        return;
      }
      if (pending) {
        // Focus/visibility bursts share a read. A saved record requires a newer snapshot.
        if (invalidatePending) {
          invalidatedGeneration = ++readGenerationRef.current;
        }
        return;
      }
      pending = true;
      const readGeneration = ++readGenerationRef.current;
      const authGeneration = getAuthGeneration();
      const isCurrent = () => isIdentityCurrent()
        && readGenerationRef.current === readGeneration && getAuthGeneration() === authGeneration;
      setError(null);
      getCustomChallengeParticipation(requestId)
        .then(async result => {
          if (!isCurrent()) return;
          hasData = true;
          setNotFound(false);
          setParticipation(result);
          if (!canClaimReward(result)) {
            claimAttempted = false;
            setClaimError(null);
            setAward(null);
            return;
          }
          if (claimAttempted || claimSettled) return;
          const scope = captureBadgeAwardScope(requestPrincipal);
          if (!scope) return;
          claimAttempted = true;
          claimPendingRef.current = true;
          setClaimPending(true);
          setClaimError(null);
          const isClaimCurrent = () => isIdentityCurrent() && getAuthGeneration() === scope.authGeneration;
          try {
            // Only this detail GET path claims; Home/list/background badge reads never finalize early.
            const claimed = await claimCustomChallengeReward(requestId);
            if (!isClaimCurrent()) return;
            // A dose invalidation needs a fresh live read, but a server-finalized result is immutable.
            if (!isCurrent() && claimed.participation.status === 'ACTIVE') {
              claimAttempted = false;
              return;
            }
            setParticipation(claimed.participation);
            setAward(claimed.award);
            claimSettled = claimed.participation.status === 'COMPLETED';
            if (!canClaimReward(claimed.participation)) claimAttempted = false;
            if (claimed.newlyAwarded && claimed.award && claimed.participation.status === 'COMPLETED') {
              enqueueBadgeAward(scope, {
                source: 'custom', awardId: claimed.award.id, participationId: claimed.award.participationId,
                name: claimed.award.badgeName, imageUrl: apiAssetUrl(claimed.award.badgeImagePath),
              }, { confirmedTransition: true });
            }
            if (claimed.newlyAwarded || JSON.stringify(claimed.participation) !== JSON.stringify(result)) {
              invalidateCustomChallengeProgress();
            }
          } catch (reason) {
            if (!isClaimCurrent() || (reason instanceof ApiError && reason.status === 401)) return;
            setClaimError(reason instanceof Error ? reason.message : '달성 결과를 확인하지 못했어요. 다시 시도해주세요.');
          } finally {
            if (isIdentityCurrent()) {
              claimPendingRef.current = false;
              setClaimPending(false);
              if (!isClaimCurrent()) claimAttempted = false;
            }
          }
        })
        .catch((reason: unknown) => {
          if (!isCurrent() || (reason instanceof ApiError && reason.status === 401)) return;
          if (!hasData && reason instanceof ApiError && reason.status === 404) setNotFound(true);
          else setError(reason instanceof Error ? reason.message : '맞춤 챌린지를 불러오지 못했어요.');
        })
        .finally(() => {
          pending = false;
          if (isIdentityCurrent() && invalidatedGeneration !== null) {
            // Cancellation also advances the generation, discarding pre-cancel queued reads.
            const shouldRefresh = invalidatedGeneration === readGenerationRef.current;
            invalidatedGeneration = null;
            if (shouldRefresh) refresh();
          }
        });
    }

    refreshRef.current = () => refresh(true);
    retryClaimRef.current = () => { claimAttempted = false; refresh(true); };
    const unsubscribe = subscribeCustomChallengeProgressInvalidation(() => refresh(true));
    const onFocus = () => refresh();
    const onVisibility = () => { if (document.visibilityState === 'visible') refresh(); };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibility);
    refresh();
    return () => {
      active = false;
      generationRef.current += 1;
      readGenerationRef.current += 1;
      unsubscribe();
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [id, pathname, principalKey]);

  async function cancelParticipation() {
    if (!participation || participation.status !== 'ACTIVE' || cancelPendingRef.current || claimPendingRef.current) return;
    const requestId = participation.id;
    const requestPrincipal = principalKey;
    const generation = generationRef.current;
    const authGeneration = getAuthGeneration();
    const isCurrent = () => generationRef.current === generation
      && principalRef.current === requestPrincipal && getAuthGeneration() === authGeneration
      && window.location.pathname === pathname;
    // A GET started before cancellation must never restore the ACTIVE snapshot.
    readGenerationRef.current += 1;
    cancelPendingRef.current = true;
    setCancelPending(true);
    setCancelError(null);
    let cancelled = false;
    try {
      const result = await cancelCustomChallenge(requestId);
      if (!isCurrent()) return;
      cancelled = true;
      setParticipation(result);
      setClaimError(null);
      setAward(null);
      setError(null);
      setCancelOpen(false);
      invalidateCustomChallengeProgress();
    } catch (reason) {
      if (!isCurrent() || (reason instanceof ApiError && reason.status === 401)) return;
      setCancelError(reason instanceof Error ? reason.message : '참여를 취소하지 못했어요. 다시 시도해주세요.');
      if (reason instanceof ApiError && reason.status === 409) {
        try {
          const latest = await getCustomChallengeParticipation(requestId);
          if (isCurrent()) {
            setParticipation(latest);
            if (latest.status === 'COMPLETED') refreshAfterCancelRef.current = true;
          }
        } catch {
          // Keep the server conflict visible; retry/close remains available.
        }
      }
    } finally {
      if (isCurrent()) {
        cancelPendingRef.current = false;
        setCancelPending(false);
        const shouldRefresh = refreshAfterCancelRef.current && !cancelled;
        refreshAfterCancelRef.current = false;
        if (shouldRefresh) refreshRef.current();
      }
    }
  }

  if (notFound) {
    return <><Header title="맞춤 챌린지" onBack={handleBack} /><main className="flex flex-col gap-4 px-page-x py-5"><h2 className="text-xl font-bold">참여 기록을 찾을 수 없어요</h2><Button variant="secondary" onClick={() => navigate('/challenges')}>챌린지로 돌아가기</Button></main></>;
  }
  if (error && !participation) {
    return <><Header title="맞춤 챌린지" onBack={handleBack} /><main className="flex flex-col gap-4 px-page-x py-5"><h2 className="text-xl font-bold">참여 기록을 불러오지 못했어요</h2><p role="alert" className="text-sm text-muted-foreground">{error}</p><Button variant="secondary" onClick={() => refreshRef.current()}>다시 불러오기</Button></main></>;
  }
  if (!participation) {
    return <><Header title="맞춤 챌린지" onBack={handleBack} /><main className="px-page-x py-5"><LoadingState label="맞춤 챌린지 참여 기록 불러오는 중">참여 기록을 불러오고 있어요.</LoadingState></main></>;
  }

  const days = customChallengeDayProgress(participation);
  const rate = progressValue(days.rate);
  const finalized = participation.status !== 'ACTIVE';
  return (
    <>
      <Header title={participation.challengeName} onBack={handleBack} className="h-auto! min-h-header py-2 [&_button]:shrink-0 [&_h1]:overflow-visible [&_h1]:whitespace-normal [&_h1]:break-words [&_h1]:[overflow-wrap:anywhere]" />
      <main className="flex flex-col gap-4 px-page-x py-5">
      <p className="text-caption font-bold text-primary">{statusLabel(participation.status)}</p>

      {error ? (
        <section role="alert" className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button variant="secondary" disabled={cancelPending || claimPending} onClick={() => refreshRef.current()}>다시 불러오기</Button>
        </section>
      ) : null}

      <section className="flex flex-col gap-3 rounded-card bg-primary-bg p-5" aria-labelledby="custom-progress-title">
        <div className="flex items-center justify-between gap-3"><h2 id="custom-progress-title" className="text-base font-bold">{finalized ? '최종 결과' : '내 진행률'}</h2><strong className="text-primary">{rate.toFixed(2)}%</strong></div>
        <div role="progressbar" aria-label="맞춤 챌린지 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={rate} className="h-2 overflow-hidden rounded-pill bg-border"><div className="h-full rounded-pill bg-primary" style={{ width: `${rate}%` }} /></div>
        <p className="text-sm text-foreground">{days.completed} / {days.target}일</p>
        <p className="text-caption text-muted-foreground">{participation.actualEndDate
          ? `${dateLabel(participation.joinedAt)} ~ ${dateLabel(participation.actualEndDate)}`
          : '예정된 목표 없음'}</p>
        {finalized ? <p className="text-caption leading-5 text-muted-foreground">{participation.status === 'CANCELLED' ? '취소 시점의 기록이에요. 기존 복용 기록은 유지되며, 지난 기록에서 확인할 수 있어요.' : participation.status === 'COMPLETED' ? '달성 시 확정된 결과예요. 이후 기록을 수정해도 결과와 배지는 유지돼요.' : '종료 시 확정된 결과예요. 이후 기록을 수정해도 결과와 배지는 유지돼요.'}</p> : null}
      </section>

      {award ? (
        <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="custom-award-title">
          <h2 id="custom-award-title" className="text-base font-bold">획득 배지</h2>
          <div className="flex items-center gap-3">
            <img src={apiAssetUrl(award.badgeImagePath)} alt={award.badgeName} className="size-14 rounded-pill object-contain" />
            <div>
              <p className="break-words text-sm font-bold text-foreground [overflow-wrap:anywhere]">{award.badgeName}</p>
              <p className="text-caption text-muted-foreground">{dateLabel(award.awardedAt)} 획득</p>
            </div>
          </div>
        </section>
      ) : null}
      {claimPending ? <p role="status" className="text-sm text-muted-foreground">달성 결과 확인 중...</p> : null}
      {claimError ? (
        <section role="alert" className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{claimError}</p>
          <Button variant="secondary" disabled={cancelPending || claimPending} onClick={() => retryClaimRef.current()}>달성 확인 다시 시도</Button>
        </section>
      ) : null}

      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="custom-target-title">
          <div className="flex items-center justify-between gap-3">
            <h2 id="custom-target-title" className="text-base font-bold">참여 대상</h2>
            <span className="shrink-0 text-caption text-muted-foreground">{participation.targets.length}개</span>
          </div>
          <ul className="mt-2 flex flex-col gap-3">
            {participation.targets.map(target => <li key={target.id} className="break-words text-sm text-foreground [overflow-wrap:anywhere]">{target.name}</li>)}
          </ul>
      </section>

      <CustomChallengeCalendar key={`${participation.id}:${participation.status}`} participation={participation} />

      <p className="text-caption leading-5 text-muted-foreground">진행률은 홈과 {participation.challengeType === 'SUPPLEMENT' ? '영양제' : '복약'} 기록을 기준으로 자동 계산돼요. 달력에서는 기록을 확인할 수 있어요.</p>
      {participation.status === 'ACTIVE' ? <Button variant="secondary" disabled={cancelPending || claimPending} onClick={() => { setCancelError(null); setCancelOpen(true); }}>챌린지 참여 취소</Button> : null}
      <Dialog open={cancelOpen} onOpenChange={open => { if (!cancelPendingRef.current) { setCancelOpen(open); if (!open) setCancelError(null); } }}>
        <DialogContent showCloseButton={!cancelPending}>
          <DialogHeader>
            <DialogTitle>챌린지 참여를 취소할까요?</DialogTitle>
            <DialogDescription className="space-y-2 break-keep">
              <span className="block">참여를 취소해도 기존 복용 기록은 삭제되지 않아요.</span>
              <span className="block">취소한 챌린지는 지난 기록에서 확인할 수 있어요.</span>
            </DialogDescription>
          </DialogHeader>
          {cancelError ? <p role="alert" className="text-sm text-danger-strong">{cancelError}</p> : null}
          <DialogFooter>
            <Button variant="secondary" disabled={cancelPending} onClick={() => setCancelOpen(false)}>돌아가기</Button>
            <Button variant="danger" disabled={cancelPending || claimPending || participation.status !== 'ACTIVE'} onClick={() => void cancelParticipation()}>{cancelPending ? '취소 중...' : '참여 취소'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </main>
    </>
  );
}
