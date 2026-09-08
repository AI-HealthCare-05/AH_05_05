import { ArrowLeft, Check } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  getChallengeParticipation,
  getUserChallengeBadges,
  submitChallengeVerification,
  type ChallengeParticipation,
  type UserChallengeBadge,
} from '@/entities/challenge';
import { ApiError } from '@/shared/api/client';
import { Button } from '@/shared/ui/Button';
import {
  challengeVerificationDates,
  inclusiveChallengeEndDate,
  trailingNonVerificationDays,
} from './officialChallengeDates';

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
  const requestGenerationRef = useRef(0);
  const idempotencyKeyRef = useRef<string | null>(null);
  const [data, setData] = useState<ParticipationData | null>(null);
  const [notFound, setNotFound] = useState(id === null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [refreshRequired, setRefreshRequired] = useState(false);
  const [pending, setPending] = useState(false);
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
    idempotencyKeyRef.current = null;
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
    return <main role="status" aria-label="참여 기록 불러오는 중" className="mx-page-x my-5 min-h-72 animate-pulse rounded-card bg-muted-bg" />;
  }

  const participation = data.participation;
  const endDate = inclusiveChallengeEndDate(participation.end_at);
  const startDate = participation.started_at.slice(0, 10);
  const verificationDates = challengeVerificationDates(participation.progress_periods);
  const nonVerificationDays = trailingNonVerificationDays(participation.progress_periods, endDate);
  const rate = progressValue(participation.progress_rate);
  const unit = unitLabel(participation);
  const badge = participation.challenge.reward_badge;
  const badgeEarned = badge && data.badges
    ? data.badges.some(item => item.badge_id === badge.id && item.status === 'AWARDED')
    : false;
  const isSelfActive = participation.status === 'ACTIVE' && participation.challenge.check_type_code === 'SELF';

  async function checkIn() {
    if (!isSelfActive || !participation.can_verify || pending) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
    );
    const key = idempotencyKeyRef.current ?? crypto.randomUUID();
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
    if (id === null || pending) return;
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

  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <header className="flex items-center gap-3">
        <button type="button" aria-label="뒤로 가기" onClick={() => navigate('/challenges')} className="flex size-11 shrink-0 items-center justify-center rounded-pill"><ArrowLeft aria-hidden className="size-5" /></button>
        <div className="min-w-0">
          <h1 className="break-words text-[22px] font-bold leading-7">{participation.challenge_name}</h1>
          <p className="text-caption text-muted-foreground">내 수행 기간 · {dateLabel(startDate)} ~ {dateLabel(endDate)}</p>
        </div>
      </header>

      {participation.today_verification?.status === 'APPROVED' ? (
        <section className="flex gap-3 rounded-card bg-primary-bg p-5" aria-label="오늘 인증 결과">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-pill bg-primary text-card"><Check aria-hidden className="size-5" /></span>
          <div><h2 className="text-base font-bold">오늘의 실천을 기록했어요</h2><p className="mt-1 text-caption text-primary">같은 날 중복으로 인증되지 않아요.</p></div>
        </section>
      ) : null}

      {refreshRequired ? (
        <section role="status" className="flex flex-col gap-2 rounded-card bg-muted-bg p-5">
          <p className="text-sm text-muted-foreground">최신 진행 정보 확인 필요</p>
          <Button variant="secondary" disabled={pending} onClick={() => void refreshParticipation()}>다시 불러오기</Button>
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
          {badge ? <img src={badge.image_path} alt={badge.name} className={`size-16 rounded-pill object-contain ${data.badges && !badgeEarned ? 'grayscale opacity-60' : ''}`} /> : null}
          <h2 className="text-lg font-bold">챌린지를 완주했어요</h2>
          {badge ? <Link to={`/challenges/badges/${badge.id}`} className="text-sm font-bold text-primary">{badge.name} 자세히 보기 ›</Link> : null}
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
      {isSelfActive ? <Button disabled={pending || !participation.can_verify} onClick={() => void checkIn()}>{checkInLabel(participation, pending)}</Button> : null}
    </main>
  );
}
