import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  getChallengeParticipations,
  getUserChallengeBadges,
  submitChallengeVerification,
  type ChallengeParticipation,
  type UserChallengeBadge,
} from '@/entities/challenge';
import { Button } from '@/shared/ui/Button';
import { ChallengePageHeading } from './ChallengePageHeading';
import { OfficialChallengeProgressCard } from './OfficialChallengeProgressCard';

interface ChallengeDashboard {
  participations: ChallengeParticipation[];
  badges: UserChallengeBadge[] | null;
  badgeError: string | null;
}

async function loadDashboard(): Promise<ChallengeDashboard> {
  const [participations, badgeResult] = await Promise.all([
    getChallengeParticipations(),
    getUserChallengeBadges()
      .then(result => ({ badges: result.items, badgeError: null }))
      .catch((reason: unknown) => ({
        badges: null,
        badgeError: reason instanceof Error ? reason.message : '배지 정보를 불러오지 못했어요.',
      })),
  ]);
  return { participations: participations.items, ...badgeResult };
}

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function OfficialChallengeMyPage() {
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const keysRef = useRef(new Map<string, string>());
  const [data, setData] = useState<ChallengeDashboard | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ id: number; message: string } | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [refreshRequiredId, setRefreshRequiredId] = useState<number | null>(null);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  principalRef.current = principalKey;

  useEffect(() => {
    let active = true;
    setData(null);
    setLoadError(null);
    setActionError(null);
    setPendingId(null);
    setRefreshRequiredId(null);
    keysRef.current.clear();
    loadDashboard()
      .then(result => {
        if (active) setData(result);
      })
      .catch((reason: unknown) => {
        if (active) setLoadError(reason instanceof Error ? reason.message : '내 챌린지를 불러오지 못했어요.');
      });
    return () => {
      active = false;
    };
  }, [principalKey, reloadKey]);

  async function checkIn(participation: ChallengeParticipation) {
    if (
      pendingId !== null ||
      participation.challenge.check_type_code !== 'SELF' ||
      !participation.can_verify
    ) return;
    const requestPrincipal = principalKey;
    const keyId = `${requestPrincipal}:${participation.id}:${participation.today}`;
    const idempotencyKey = keysRef.current.get(keyId) ?? newIdempotencyKey();
    keysRef.current.set(keyId, idempotencyKey);
    setPendingId(participation.id);
    setActionError(null);
    try {
      const verification = await submitChallengeVerification(participation.id, {
        verification_date: participation.today,
        idempotency_key: idempotencyKey,
      });
      if (principalRef.current !== requestPrincipal) return;
      keysRef.current.delete(keyId);
      setData(current => current ? {
        ...current,
        participations: current.participations.map(item => item.id === participation.id
          ? {
              ...item,
              today_verification: verification,
              can_verify: false,
              verified_dates: item.verified_dates.includes(verification.verification_date)
                ? item.verified_dates
                : [...item.verified_dates, verification.verification_date],
            }
          : item),
      } : current);
      try {
        const refreshed = await loadDashboard();
        if (principalRef.current !== requestPrincipal) return;
        setData(refreshed);
        setRefreshRequiredId(null);
      } catch {
        if (principalRef.current !== requestPrincipal) return;
        setRefreshRequiredId(participation.id);
      }
    } catch (reason) {
      if (principalRef.current !== requestPrincipal) return;
      setActionError({
        id: participation.id,
        message: reason instanceof Error ? reason.message : '인증을 기록하지 못했어요.',
      });
    } finally {
      if (principalRef.current === requestPrincipal) setPendingId(null);
    }
  }

  async function refreshDashboard(participationId: number) {
    if (pendingId !== null) return;
    const requestPrincipal = principalKey;
    setPendingId(participationId);
    setActionError(null);
    try {
      const refreshed = await loadDashboard();
      if (principalRef.current !== requestPrincipal) return;
      setData(refreshed);
      setRefreshRequiredId(null);
    } catch (reason) {
      if (principalRef.current !== requestPrincipal) return;
      setActionError({
        id: participationId,
        message: reason instanceof Error ? reason.message : '최신 진행 정보를 불러오지 못했어요.',
      });
    } finally {
      if (principalRef.current === requestPrincipal) setPendingId(null);
    }
  }

  if (loadError) {
    return (
      <main className="flex flex-col gap-4 px-page-x py-5">
        <ChallengePageHeading />
        <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex flex-col gap-4 px-page-x py-5">
        <ChallengePageHeading />
        <div role="status" aria-label="내 챌린지 불러오는 중" className="min-h-72 animate-pulse rounded-card bg-muted-bg" />
      </main>
    );
  }

  const active = data.participations.filter(item => item.status === 'ACTIVE');
  const history = data.participations.filter(item => item.status !== 'ACTIVE');
  const awarded = data.badges?.filter(item => item.status === 'AWARDED') ?? [];
  const earnedKinds = new Set(awarded.map(item => item.badge_id));

  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <ChallengePageHeading />
      <nav aria-label="챌린지 보기" className="grid h-11 grid-cols-2 rounded-input bg-muted-bg p-1">
        <Link aria-current="page" to="/challenges" className="flex items-center justify-center rounded-[9px] bg-card text-sm font-bold text-primary shadow-card">마이</Link>
        <Link to="/challenges/browse" className="flex items-center justify-center rounded-[9px] text-sm font-medium text-muted-foreground">둘러보기</Link>
      </nav>

      <section className="flex flex-col gap-3 rounded-card bg-primary-bg p-5" aria-labelledby="badge-summary-title">
        <h2 id="badge-summary-title" className="text-base font-bold">작은 실천이 쌓이고 있어요</h2>
        <div className="flex items-center justify-between gap-3 text-caption text-primary">
          {data.badgeError
            ? <span role="alert" className="text-muted-foreground">{data.badgeError}</span>
            : <span>모은 배지 {earnedKinds.size}종 · {awarded.length}회 획득</span>}
          <Link to="/challenges/badges" className="font-bold">전체 보기 ›</Link>
        </div>
        <div className="flex gap-3" aria-label="최근 획득 배지">
          {awarded.slice(0, 3).map(item => <img key={item.id} src={item.badge_image_path} alt={item.badge_name} className="size-9 rounded-pill object-contain" />)}
        </div>
      </section>

      <section aria-labelledby="active-challenges-title" className="flex flex-col gap-3">
        <h2 id="active-challenges-title" className="text-base font-bold">진행 중인 챌린지</h2>
        {active.length === 0 ? (
          <div className="flex flex-col gap-3 rounded-card bg-card p-5 text-sm text-muted-foreground shadow-card">
            <p>참여 중인 챌린지가 없어요.</p>
            <Link to="/challenges/browse" className="font-bold text-primary">공식 챌린지 둘러보기 ›</Link>
          </div>
        ) : active.map(item => (
          <OfficialChallengeProgressCard
            key={item.id}
            participation={item}
            pending={pendingId === item.id}
            error={actionError?.id === item.id ? actionError.message : undefined}
            refreshRequired={refreshRequiredId === item.id}
            onCheckIn={() => void checkIn(item)}
            onRefresh={() => void refreshDashboard(item.id)}
          />
        ))}
      </section>

      {history.length > 0 ? (
        <section aria-labelledby="challenge-history-title" className="flex flex-col gap-3">
          <div className="flex min-h-touch items-center justify-between gap-3">
            <h2 id="challenge-history-title" className="text-base font-bold">지난 기록</h2>
            <button type="button" aria-expanded={historyExpanded} aria-label={historyExpanded ? '지난 기록 접기' : '지난 기록 펼치기'} onClick={() => setHistoryExpanded(value => !value)} className="min-h-touch rounded-pill px-3 text-sm font-bold text-primary">
              {historyExpanded ? '접기' : `${history.length}개 보기`}
            </button>
          </div>
          {historyExpanded ? history.map(item => (
            <OfficialChallengeProgressCard key={item.id} participation={item} pending={false} onCheckIn={() => undefined} />
          )) : null}
        </section>
      ) : null}
    </main>
  );
}
