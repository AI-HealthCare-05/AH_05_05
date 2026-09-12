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
import { LoadingState } from '@/shared/ui/LoadingState';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { ChallengePageHeading } from './ChallengePageHeading';
import { OfficialChallengeProgressCard } from './OfficialChallengeProgressCard';
import { CustomChallengeProgressCard } from './CustomChallengeProgressCard';
import { useCustomChallengeMy } from './useCustomChallengeMy';
import { ChallengeAccordion } from './ChallengeAccordion';

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
  const custom = useCustomChallengeMy();
  const principalRef = useRef(principalKey);
  const requestGenerationRef = useRef(0);
  const keysRef = useRef(new Map<string, string>());
  const pendingRef = useRef(false);
  const [data, setData] = useState<ChallengeDashboard | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ id: number; message: string } | null>(null);
  const [pendingId, setPendingId] = useState<number | 'badges' | null>(null);
  const [refreshRequiredIds, setRefreshRequiredIds] = useState<Set<number>>(() => new Set());
  const [reloadKey, setReloadKey] = useState(0);
  principalRef.current = principalKey;

  useEffect(() => {
    requestGenerationRef.current += 1;
    return () => {
      requestGenerationRef.current += 1;
    };
  }, [principalKey]);

  useEffect(() => {
    let active = true;
    setData(null);
    setLoadError(null);
    setActionError(null);
    setPendingId(null);
    setRefreshRequiredIds(new Set());
    pendingRef.current = false;
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
      pendingRef.current ||
      participation.challenge.check_type_code !== 'SELF' ||
      !participation.can_verify
    ) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
    );
    const keyId = `${requestPrincipal}:${participation.id}:${participation.today}`;
    const idempotencyKey = keysRef.current.get(keyId) ?? newIdempotencyKey();
    keysRef.current.set(keyId, idempotencyKey);
    pendingRef.current = true;
    setPendingId(participation.id);
    setActionError(null);
    try {
      const verification = await submitChallengeVerification(participation.id, {
        verification_date: participation.today,
        idempotency_key: idempotencyKey,
      });
      if (!isCurrentRequest()) return;
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
        if (!isCurrentRequest()) return;
        setData(refreshed);
        setRefreshRequiredIds(new Set());
      } catch {
        if (!isCurrentRequest()) return;
        setRefreshRequiredIds(current => new Set(current).add(participation.id));
      }
    } catch (reason) {
      if (!isCurrentRequest()) return;
      setActionError({
        id: participation.id,
        message: reason instanceof Error ? reason.message : '인증을 기록하지 못했어요.',
      });
    } finally {
      if (isCurrentRequest()) {
        pendingRef.current = false;
        setPendingId(null);
      }
    }
  }

  async function refreshDashboard(target: number | 'badges') {
    if (pendingRef.current) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
    );
    pendingRef.current = true;
    setPendingId(target);
    setActionError(null);
    try {
      const refreshed = await loadDashboard();
      if (!isCurrentRequest()) return;
      setData(refreshed);
      setRefreshRequiredIds(new Set());
    } catch (reason) {
      if (!isCurrentRequest()) return;
      const message = reason instanceof Error ? reason.message : '최신 진행 정보를 불러오지 못했어요.';
      if (target === 'badges') {
        setData(current => current ? { ...current, badgeError: message } : current);
      } else {
        setActionError({ id: target, message });
      }
    } finally {
      if (isCurrentRequest()) {
        pendingRef.current = false;
        setPendingId(null);
      }
    }
  }

  const active = data?.participations.filter(item => item.status === 'ACTIVE') ?? [];
  const history = data?.participations.filter(item => item.status !== 'ACTIVE') ?? [];
  const customActive = custom.items?.filter(item => item.status === 'ACTIVE') ?? [];
  const customHistory = custom.items?.filter(item => item.status !== 'ACTIVE') ?? [];
  const historyCount = history.length + customHistory.length;
  const emptyActive = data !== null && custom.items !== null && active.length + customActive.length === 0;
  const awarded = data?.badges?.filter(item => item.status === 'AWARDED') ?? [];
  const earnedKinds = new Set(awarded.map(item => item.badge_id));
  const badgeRefreshRequired = refreshRequiredIds.size > 0 || data?.badgeError !== null;

  return (
    <>
      <ChallengePageHeading />
      <main className="flex flex-col gap-4 px-page-x py-5">
      <nav aria-label="챌린지 보기" className="grid h-11 grid-cols-2 rounded-input bg-muted-bg p-1">
        <Link aria-current="page" to="/challenges" className="flex items-center justify-center rounded-[9px] bg-card text-sm font-bold text-primary shadow-card">나의 챌린지</Link>
        <Link to="/challenges/browse" className="flex items-center justify-center rounded-[9px] text-sm font-medium text-muted-foreground">둘러보기</Link>
      </nav>

      {loadError ? (
        <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button>
        </div>
      ) : null}
      {!data && !loadError ? (
        <LoadingState label="내 챌린지 불러오는 중">내 챌린지를 불러오고 있어요.</LoadingState>
      ) : null}

      {data ? (
        <>
      <section className="flex flex-col gap-3 rounded-card bg-primary-bg p-5" aria-labelledby="badge-summary-title">
        <h2 id="badge-summary-title" className="text-base font-bold">작은 실천이 쌓이고 있어요</h2>
        <div className="flex items-center justify-between gap-3 text-caption text-primary">
          {badgeRefreshRequired ? (
            <div className="flex flex-1 flex-col gap-2">
              {data.badgeError
                ? <span role="alert" className="text-muted-foreground">{data.badgeError}</span>
                : <span role="status" className="text-muted-foreground">최신 배지 정보 확인 필요</span>}
              <Button
                variant="secondary"
                onClick={() => void refreshDashboard('badges')}
                disabled={pendingId !== null}
                className="h-11 min-h-11"
              >
                배지 다시 불러오기
              </Button>
            </div>
          ) : <span>모은 배지 {earnedKinds.size}종 · {awarded.length}회 획득</span>}
          <Link to="/challenges/badges" className="font-bold">전체 보기 ›</Link>
        </div>
        {badgeRefreshRequired ? null : (
          <div className="flex gap-3" aria-label="최근 획득 배지">
            {awarded.slice(0, 3).map(item => <img key={item.id} src={apiAssetUrl(item.badge_image_path)} alt={item.badge_name} className="size-9 rounded-pill object-contain" />)}
          </div>
        )}
      </section>
        </>
      ) : null}

      <ChallengeAccordion key={`${principalKey}-active`} title="진행 중인 챌린지" count={data && custom.items ? active.length + customActive.length : undefined}>
        {custom.items === null && !custom.error ? <LoadingState label="내 맞춤 챌린지 불러오는 중">맞춤 챌린지를 불러오고 있어요.</LoadingState> : null}
        {custom.error ? (
          <div role="alert" className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card">
            <p className="text-sm text-muted-foreground">{custom.error}</p>
            <Button variant="secondary" onClick={custom.reload}>맞춤 챌린지 다시 불러오기</Button>
          </div>
        ) : null}
        {emptyActive ? (
          <div className="flex flex-col gap-3 rounded-card bg-card p-5 text-sm text-muted-foreground shadow-card">
            <p>참여 중인 챌린지가 없어요.</p>
          </div>
        ) : null}
        {active.map(item => (
          <OfficialChallengeProgressCard
            key={`official-${item.id}`}
            participation={item}
            pending={pendingId === item.id}
            error={actionError?.id === item.id ? actionError.message : undefined}
            refreshRequired={refreshRequiredIds.has(item.id)}
            onCheckIn={() => void checkIn(item)}
            onRefresh={() => void refreshDashboard(item.id)}
          />
        ))}
        {customActive.map(item => <CustomChallengeProgressCard key={`custom-${item.id}`} participation={item} />)}
      </ChallengeAccordion>

        <ChallengeAccordion key={`${principalKey}-history`} title="지난 기록" count={data && custom.items ? historyCount : undefined}>
          {data && custom.items && historyCount === 0 && <p className="px-2 py-3 text-sm text-muted-foreground">지난 기록이 없어요.</p>}
          {history.map(item => (
            <OfficialChallengeProgressCard key={`official-${item.id}`} participation={item} pending={false} onCheckIn={() => undefined} />
          ))}
          {customHistory.map(item => <CustomChallengeProgressCard key={`custom-${item.id}`} participation={item} />)}
        </ChallengeAccordion>
      </main>
    </>
  );
}
