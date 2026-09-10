import { Check } from 'lucide-react';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  cancelOfficialChallenge,
  getChallengeParticipation,
  getUserChallengeBadges,
  joinOfficialChallenge,
  submitChallengeVerification,
  type ChallengeParticipation,
  type UserChallengeBadge,
} from '@/entities/challenge';
import { ApiError } from '@/shared/api/client';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { Button } from '@/shared/ui/Button';
import { Header } from '@/shared/ui/Header';
import { LoadingState } from '@/shared/ui/LoadingState';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog';
import {
  challengeVerificationDates,
  inclusiveChallengeEndDate,
  trailingNonVerificationDays,
} from './officialChallengeDates';
import { OfficialChallengeRejoinDialog } from './OfficialChallengeRejoinDialog';

function positiveId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

function dateLabel(value: string) {
  const [year, month, day] = value.slice(0, 10).split('-');
  return `${year}.${Number(month)}.${Number(day)}`;
}

function progressValue(value: number | string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(100, Math.max(0, parsed)) : 0;
}

function usesWaterBadgeContour(imagePath: string) {
  return /(^|\/)water-badge\.png(?:[?#].*)?$/i.test(imagePath);
}

function unitLabel(participation: ChallengeParticipation) {
  return participation.challenge.frequency_code === 'DAILY' ? '일 인증' : '회 인증';
}

function checkInLabel(participation: ChallengeParticipation, pending: boolean) {
  if (pending) return '인증 기록 중';
  if (participation.today_verification?.status === 'APPROVED') return '오늘 인증 완료';
  if (participation.today_verification?.status === 'PENDING') return '인증 확인 중';
  if (participation.today_verification?.status === 'REJECTED') return '인증이 반려됐어요';
  if (!participation.can_verify) return '오늘은 인증할 수 없어요';
  return '했어요';
}

interface ParticipationData {
  participation: ChallengeParticipation;
  badges: UserChallengeBadge[] | null;
  badgeError: string | null;
}

async function loadParticipationData(id: number): Promise<ParticipationData> {
  const [participation, badgeResult] = await Promise.all([
    getChallengeParticipation(id),
    getUserChallengeBadges()
      .then(result => ({ badges: result.items, badgeError: null }))
      .catch((reason: unknown) => ({
        badges: null,
        badgeError: reason instanceof Error ? reason.message : '배지 정보를 불러오지 못했어요.',
      })),
  ]);
  return { participation, ...badgeResult };
}

export function OfficialChallengeParticipationPage() {
  const { participationId } = useParams();
  const id = positiveId(participationId);
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);

  function goBack() {
    const index = window.history.state?.idx;
    if (typeof index === 'number' && index > 0) {
      navigate(-1);
      return;
    }
    navigate('/challenges', { replace: true });
  }

  const requestGenerationRef = useRef(0);
  const idempotencyKeyRef = useRef<string | null>(null);
  const cancelRequestRef = useRef<symbol | null>(null);
  const rejoinRequestRef = useRef<symbol | null>(null);
  const [data, setData] = useState<ParticipationData | null>(null);
  const [notFound, setNotFound] = useState(id === null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [refreshRequired, setRefreshRequired] = useState(false);
  const [pending, setPending] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelPending, setCancelPending] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [rejoinOpen, setRejoinOpen] = useState(false);
  const [rejoinPending, setRejoinPending] = useState(false);
  const [newAwardId, setNewAwardId] = useState<number | null>(null);
  const [awardArtReady, setAwardArtReady] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  principalRef.current = principalKey;

  useEffect(() => {
    requestGenerationRef.current += 1;
    return () => {
      requestGenerationRef.current += 1;
    };
  }, [id, principalKey]);

  useEffect(() => {
    if (id === null) return;
    let active = true;
    setData(null);
    setNotFound(false);
    setLoadError(null);
    setActionError(null);
    setRefreshRequired(false);
    setPending(false);
    setCancelOpen(false);
    setCancelPending(false);
    setCancelError(null);
    setRejoinOpen(false);
    setRejoinPending(false);
    setNewAwardId(null);
    setAwardArtReady(false);
    idempotencyKeyRef.current = null;
    cancelRequestRef.current = null;
    rejoinRequestRef.current = null;
    loadParticipationData(id)
      .then(result => {
        if (active) setData(result);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 404) setNotFound(true);
        else setLoadError(reason instanceof Error ? reason.message : '참여 기록을 불러오지 못했어요.');
      });
    return () => {
      active = false;
    };
  }, [id, principalKey, reloadKey]);

  if (notFound) {
    return (
      <main className="flex flex-col gap-4 px-page-x py-5">
        <h1 className="text-xl font-bold">참여 기록을 찾을 수 없어요</h1>
        <Button variant="secondary" onClick={() => navigate('/challenges')}>챌린지로 돌아가기</Button>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex flex-col gap-4 px-page-x py-5">
        <h1 className="text-xl font-bold">참여 기록을 불러오지 못했어요</h1>
        <p role="alert" className="text-sm text-muted-foreground">{loadError}</p>
        <Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button>
      </main>
    );
  }

  if (!data) {
    return <><Header title="챌린지" onBack={() => navigate('/challenges')} /><main className="px-page-x py-5"><LoadingState label="참여 기록 불러오는 중">참여 기록을 불러오고 있어요.</LoadingState></main></>;
  }

  const participation = data.participation;
  const endDate = inclusiveChallengeEndDate(participation.end_at);
  const startDate = participation.started_at.slice(0, 10);
  const verificationDates = challengeVerificationDates(participation.progress_periods);
  const nonVerificationDays = trailingNonVerificationDays(participation.progress_periods, endDate);
  const rate = progressValue(participation.progress_rate);
  const unit = unitLabel(participation);
  const badge = participation.challenge.reward_badge;
  const waterBadgeContour = badge ? usesWaterBadgeContour(badge.image_path) : false;
  const badgeEarned = badge && data.badges
    ? data.badges.some(item => item.badge_id === badge.id && item.status === 'AWARDED')
    : false;
  const isSelfActive = participation.status === 'ACTIVE' && participation.challenge.check_type_code === 'SELF';
  const latestId = participation.challenge.participation_id;
  const hasNewerAttempt = latestId !== null && latestId !== participation.id;
  const recruitmentClosed = participation.today > participation.challenge.recruit_end_at.slice(0, 10)
    || Date.now() >= new Date(participation.challenge.recruit_end_at).getTime();
  const canRejoin = participation.status === 'CANCELLED'
    && participation.challenge.check_type_code === 'SELF'
    && participation.challenge.can_join;

  async function rejoin() {
    if (!canRejoin || rejoinRequestRef.current !== null) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const requestToken = Symbol('rejoin-challenge');
    rejoinRequestRef.current = requestToken;
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
      && rejoinRequestRef.current === requestToken
    );
    setRejoinPending(true);
    setActionError(null);
    try {
      const joined = await joinOfficialChallenge(participation.challenge_id);
      if (!isCurrentRequest()) return;
      navigate(`/challenges/participations/${joined.id}`, { replace: true });
    } catch (reason) {
      if (!isCurrentRequest()) return;
      if (!(reason instanceof ApiError) || reason.status === 409 || reason.status >= 500) {
        try {
          const refreshed = await loadParticipationData(participation.id);
          if (!isCurrentRequest()) return;
          setData(refreshed);
          const challenge = refreshed.participation.challenge;
          if (!challenge.can_join && challenge.participation_id && challenge.participation_id !== participation.id) {
            navigate(`/challenges/participations/${challenge.participation_id}`, { replace: true });
            return;
          }
        } catch {
          if (!isCurrentRequest()) return;
        }
      }
      setRejoinOpen(false);
      setActionError(reason instanceof Error ? reason.message : '챌린지에 다시 참여하지 못했어요.');
    } finally {
      if (isCurrentRequest()) {
        rejoinRequestRef.current = null;
        setRejoinPending(false);
      }
    }
  }

  async function checkIn() {
    if (!isSelfActive || !participation.can_verify || pending || cancelPending) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
    );
    const key = idempotencyKeyRef.current ?? crypto.randomUUID();
    const previousAwardIds = new Set(
      data?.badges?.filter(item => item.status === 'AWARDED').map(item => item.id) ?? [],
    );
    idempotencyKeyRef.current = key;
    setPending(true);
    setActionError(null);
    try {
      const verification = await submitChallengeVerification(participation.id, {
        verification_date: participation.today,
        idempotency_key: key,
      });
      if (!isCurrentRequest()) return;
      idempotencyKeyRef.current = null;
      setData(current => current ? {
        ...current,
        participation: {
          ...current.participation,
          today_verification: verification,
          can_verify: false,
          verified_dates: current.participation.verified_dates.includes(verification.verification_date)
            ? current.participation.verified_dates
            : [...current.participation.verified_dates, verification.verification_date],
        },
      } : current);
      try {
        const refreshed = await loadParticipationData(participation.id);
        if (!isCurrentRequest()) return;
        const newlyAwarded = refreshed.badges?.find(item => (
          item.status === 'AWARDED'
          && item.badge_id === participation.challenge.reward_badge?.id
          && !previousAwardIds.has(item.id)
        ));
        setAwardArtReady(false);
        setNewAwardId(newlyAwarded?.badge_id ?? null);
        setData(refreshed);
        setRefreshRequired(false);
      } catch {
        if (!isCurrentRequest()) return;
        setRefreshRequired(true);
      }
    } catch (reason) {
      if (!isCurrentRequest()) return;
      setActionError(reason instanceof Error ? reason.message : '인증을 기록하지 못했어요.');
    } finally {
      if (isCurrentRequest()) setPending(false);
    }
  }

  async function refreshParticipation() {
    if (id === null || pending || cancelPending) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
    );
    setPending(true);
    setActionError(null);
    try {
      const refreshed = await loadParticipationData(id);
      if (!isCurrentRequest()) return;
      setData(refreshed);
      setRefreshRequired(false);
    } catch (reason) {
      if (!isCurrentRequest()) return;
      setActionError(reason instanceof Error ? reason.message : '최신 진행 정보를 불러오지 못했어요.');
    } finally {
      if (isCurrentRequest()) setPending(false);
    }
  }

  function openCancelDialog() {
    if (participation.status !== 'ACTIVE' || pending || cancelPending || refreshRequired) return;
    setCancelError(null);
    setCancelOpen(true);
  }

  async function cancelParticipation() {
    if (
      participation.status !== 'ACTIVE'
      || pending
      || refreshRequired
      || cancelRequestRef.current !== null
    ) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const requestToken = Symbol('cancel-participation');
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
      && cancelRequestRef.current === requestToken
    );
    cancelRequestRef.current = requestToken;
    setCancelPending(true);
    setCancelError(null);
    try {
      const cancelled = await cancelOfficialChallenge(participation.id);
      if (!isCurrentRequest()) return;
      setData(current => current && current.participation.id === cancelled.id
        ? { ...current, participation: cancelled }
        : current);
      setCancelOpen(false);
    } catch (reason) {
      if (!isCurrentRequest()) return;
      if (reason instanceof ApiError && reason.status === 401) return;
      setCancelError(reason instanceof Error ? reason.message : '챌린지 참여를 취소하지 못했어요.');
    } finally {
      if (cancelRequestRef.current === requestToken) {
        cancelRequestRef.current = null;
        if (
          principalRef.current === requestPrincipal
          && requestGenerationRef.current === requestGeneration
        ) setCancelPending(false);
      }
    }
  }

  return (
    <>
    <Header title={participation.challenge_name} onBack={goBack} className="h-auto! min-h-header py-2 [&_button]:shrink-0 [&_h1]:overflow-visible [&_h1]:whitespace-normal [&_h1]:break-words [&_h1]:[overflow-wrap:anywhere]" />
    <main className="flex flex-col gap-4 px-page-x py-5">
      <p className="text-caption text-muted-foreground">내 수행 기간 · {dateLabel(startDate)} ~ {dateLabel(endDate)}</p>

      {participation.today_verification?.status === 'APPROVED' ? (
        <section className="flex gap-3 rounded-card bg-primary-bg p-5" aria-label="오늘 인증 결과">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-pill bg-primary text-card"><Check aria-hidden className="size-5" /></span>
          <div><h2 className="text-base font-bold">오늘의 실천을 기록했어요</h2><p className="mt-1 text-caption text-primary">같은 날 중복으로 인증되지 않아요.</p></div>
        </section>
      ) : null}

      {refreshRequired ? (
        <section role="status" className="flex flex-col gap-2 rounded-card bg-muted-bg p-5">
          <p className="text-sm text-muted-foreground">최신 진행 정보 확인 필요</p>
          <Button variant="secondary" disabled={pending || cancelPending} onClick={() => void refreshParticipation()}>다시 불러오기</Button>
        </section>
      ) : null}

      {participation.status === 'ACTIVE' && !refreshRequired ? (
        <section className="flex flex-col gap-2 rounded-card bg-primary-bg p-5" aria-label="오늘의 챌린지 진행">
          <h2 className="text-base font-bold">오늘도 한 걸음</h2>
          <p className="text-sm text-primary">{participation.completed_count} / {participation.target_count}{unit} · {checkInLabel(participation, false)}</p>
          <div className="h-2 overflow-hidden rounded-pill bg-border"><div className="h-full rounded-pill bg-primary" style={{ width: `${rate}%` }} /></div>
        </section>
      ) : null}

      {participation.status === 'COMPLETED' ? (
        <section className="flex flex-col items-center gap-2 rounded-card bg-primary-bg p-5 text-center" aria-label="챌린지 완료 결과">
          {badge ? <img src={apiAssetUrl(badge.image_path)} alt={badge.name} data-award-contour={waterBadgeContour ? 'water' : undefined} data-newly-awarded={newAwardId === badge.id ? 'true' : undefined} data-award-art-ready={newAwardId === badge.id && awardArtReady ? 'true' : undefined} onLoad={(event) => { if (newAwardId !== badge.id) return; const image = event.currentTarget; void image.decode().catch(() => undefined).then(() => { if (image.isConnected && image.complete && image.naturalWidth > 0) setAwardArtReady(true); }); }} className={`size-16 object-contain ${waterBadgeContour ? 'rx-badge-contour-water' : 'rounded-pill'} ${data.badges && !badgeEarned ? 'grayscale opacity-60' : ''} ${newAwardId === badge.id && awardArtReady ? 'rx-badge-award' : ''}`} /> : null}
          <h2 className="text-lg font-bold">챌린지를 완주했어요</h2>
          {badge ? <Link to={`/challenges/badges/${badge.id}`} className="text-sm font-bold text-primary">{badge.name} 자세히 보기 <DrawnChevron direction="right" className="inline size-3.5 align-middle" /></Link> : null}
        </section>
      ) : null}

      {participation.status === 'CANCELLED' || participation.status === 'EXPIRED' ? (
        <section className="rounded-card bg-muted-bg p-5 text-center"><h2 className="text-base font-bold">이번 도전은 여기까지예요</h2><p className="mt-1 text-caption text-muted-foreground">남긴 기록은 지난 기록에서 언제든 볼 수 있어요.</p></section>
      ) : null}

      <section className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card" aria-labelledby="my-record-title">
        <div className="flex items-center justify-between gap-3"><h2 id="my-record-title" className="text-base font-bold">내 인증 기록</h2>{!refreshRequired ? <span className="text-sm font-bold text-primary">{participation.completed_count} / {participation.target_count}{unit}</span> : null}</div>
        <div className="grid grid-cols-7 gap-1" aria-label="날짜별 인증 기록">
          {verificationDates.map(date => {
            const checked = participation.verified_dates.includes(date);
            return <div key={date} className="flex min-w-0 flex-col items-center gap-1"><span className="text-micro text-muted-foreground">{Number(date.slice(-2))}</span><span aria-label={`${date} ${checked ? '인증 완료' : '미인증'}`} className={`flex aspect-square w-full max-w-9 items-center justify-center rounded-[5px] ${checked ? 'bg-primary text-card' : 'bg-muted-bg text-tertiary-foreground'}`}>{checked ? <Check aria-hidden className="size-4" /> : '·'}</span></div>;
          })}
        </div>
        {nonVerificationDays > 0 ? <p className="text-caption text-muted-foreground">수행 기간의 마지막 {nonVerificationDays}일은 인증 집계 대상이 아니에요.</p> : null}
        {!refreshRequired ? <div role="progressbar" aria-label="내 인증 기록 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={rate} className="h-2 overflow-hidden rounded-pill bg-border"><div className="h-full rounded-pill bg-primary" style={{ width: `${rate}%` }} /></div> : null}
      </section>

      <section className="rounded-card bg-card p-5 shadow-card" aria-labelledby="today-goal-title"><h2 id="today-goal-title" className="text-base font-bold">오늘의 목표</h2><p className="mt-1 text-sm text-muted-foreground">{participation.challenge.phrase}</p></section>
      <section className="rounded-card bg-card p-5 text-caption text-muted-foreground shadow-card" aria-labelledby="certification-note-title"><h2 id="certification-note-title" className="mb-2 text-base font-bold text-foreground">배지와 인증 안내</h2><p>{participation.challenge.check_type_code === 'SELF' ? '인증 내용은 내가 누른 기록을 기준으로 해요.' : '관리자 확인 방식은 현재 앱에서 인증할 수 없어요.'}</p></section>

      {actionError ? <p role="alert" className="text-sm text-danger-strong">{actionError}</p> : null}
      {data.badgeError ? <p role="alert" className="text-sm text-muted-foreground">{data.badgeError}</p> : null}
      {isSelfActive ? <Button disabled={pending || cancelPending || !participation.can_verify} onClick={() => void checkIn()}>{checkInLabel(participation, pending)}</Button> : null}
      {participation.status === 'ACTIVE' ? (
        <Button
          variant="secondary"
          disabled={pending || cancelPending || refreshRequired}
          onClick={openCancelDialog}
        >
          챌린지 참여 취소
        </Button>
      ) : null}

      {participation.status === 'CANCELLED' ? canRejoin ? (
        <Button disabled={rejoinPending} onClick={() => setRejoinOpen(true)}>다시 참여하기</Button>
      ) : hasNewerAttempt ? (
        <Button onClick={() => navigate(`/challenges/participations/${latestId}`, { replace: true })}>진행 보기</Button>
      ) : (
        <p className="text-center text-sm text-muted-foreground">{recruitmentClosed ? '모집이 마감됐어요' : '지금은 다시 참여할 수 없어요'}</p>
      ) : null}

      <OfficialChallengeRejoinDialog open={rejoinOpen} pending={rejoinPending} onOpenChange={setRejoinOpen} onConfirm={() => void rejoin()} />

      <Dialog
        open={cancelOpen}
        onOpenChange={open => {
          if (cancelPending) return;
          setCancelOpen(open);
          if (!open) setCancelError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>챌린지 참여를 취소할까요?</DialogTitle>
            <DialogDescription className="space-y-2 break-keep">
              <span className="block">참여를 취소해도 이전 기록은 보관돼요.</span>
              <span className="block">모집 기간 안에는 다시 참여할 수 있어요.</span>
              <span className="block">다시 참여하면 새 수행 기간과 진행률 0%로 시작해요.</span>
            </DialogDescription>
          </DialogHeader>
          {cancelError ? <p role="alert" className="text-sm text-danger-strong">{cancelError}</p> : null}
          <DialogFooter>
            <Button variant="secondary" disabled={cancelPending} onClick={() => setCancelOpen(false)}>돌아가기</Button>
            <Button variant="danger" disabled={cancelPending} onClick={() => void cancelParticipation()}>
              {cancelPending ? '취소 중...' : '참여 취소'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
    </>
  );
}
