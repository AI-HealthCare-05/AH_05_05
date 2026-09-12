import { ChevronDown } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import {
  getChallengeCatalogItem,
  joinOfficialChallenge,
  type ChallengeCatalogItem,
} from '@/entities/challenge';
import { useSession } from '@/app/SessionContext';
import { ApiError } from '@/shared/api/client';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { Button } from '@/shared/ui/Button';
import { Header } from '@/shared/ui/Header';
import { LoadingState } from '@/shared/ui/LoadingState';
import { navigateBackOrReplace } from '@/shared/lib/navigation';
import { koreanChallengeDate } from './officialChallengeDates';
import { OfficialChallengeRejoinDialog } from './OfficialChallengeRejoinDialog';

function positiveId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

function positiveParticipationId(value: number | null): number | null {
  return Number.isSafeInteger(value) && Number(value) > 0 ? value : null;
}

function shouldReconcileJoinFailure(reason: unknown): boolean {
  if (!(reason instanceof ApiError)) return true;
  return reason.status >= 500
    || reason.status === 409;
}

function targetLabel(item: ChallengeCatalogItem) {
  if (item.frequency_code === 'DAILY') return '매일 한 번';
  if (item.frequency_code === 'WEEKLY_3') return '주 3회';
  if (item.frequency_code === 'TOTAL_10') return '기간 동안 총 10회';
  return '상세 운영 기준에 따라 인증';
}

export function OfficialChallengeDetailPage() {
  const { challengeId } = useParams();
  const id = positiveId(challengeId);
  const navigate = useNavigate();
  const goBack = () => navigateBackOrReplace(navigate, '/challenges/browse');
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const requestGenerationRef = useRef(0);
  const joinRequestRef = useRef<symbol | null>(null);
  const [item, setItem] = useState<ChallengeCatalogItem | null>(null);
  const [notFound, setNotFound] = useState(id === null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [rejoinOpen, setRejoinOpen] = useState(false);
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
    setItem(null);
    setNotFound(false);
    setLoadError(null);
    setJoinError(null);
    setPending(false);
    setRejoinOpen(false);
    joinRequestRef.current = null;
    getChallengeCatalogItem(id)
      .then(result => {
        if (active) setItem(result);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 404) setNotFound(true);
        else setLoadError(reason instanceof Error ? reason.message : '챌린지를 불러오지 못했어요.');
      });
    return () => {
      active = false;
    };
  }, [id, principalKey, reloadKey]);

  if (notFound) {
    return (
      <main className="flex flex-col gap-4 px-page-x py-5">
        <h1 className="text-xl font-bold">챌린지를 찾을 수 없어요</h1>
        <Button variant="secondary" onClick={goBack}>둘러보기로 돌아가기</Button>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex flex-col gap-4 px-page-x py-5">
        <h1 className="text-xl font-bold">챌린지를 불러오지 못했어요</h1>
        <p role="alert" className="text-sm text-muted-foreground">{loadError}</p>
        <Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button>
      </main>
    );
  }

  if (!item) {
    return <><Header title="챌린지" onBack={goBack} /><main className="px-page-x py-5"><LoadingState label="챌린지 상세 불러오는 중">챌린지를 불러오고 있어요.</LoadingState></main></>;
  }

  const selfCheck = item.check_type_code === 'SELF';
  const canJoin = selfCheck && item.can_join;

  async function join() {
    if (!canJoin || joinRequestRef.current !== null) return;
    const requestPrincipal = principalKey;
    const requestGeneration = requestGenerationRef.current;
    const requestToken = Symbol('join-challenge');
    joinRequestRef.current = requestToken;
    const isCurrentRequest = () => (
      principalRef.current === requestPrincipal
      && requestGenerationRef.current === requestGeneration
      && joinRequestRef.current === requestToken
    );
    setPending(true);
    setJoinError(null);
    try {
      const participation = await joinOfficialChallenge(item!.id);
      if (!isCurrentRequest()) return;
      navigate(`/challenges/participations/${participation.id}`, { replace: Boolean(item!.participation_id) });
    } catch (reason) {
      if (!isCurrentRequest()) return;
      if (shouldReconcileJoinFailure(reason)) {
        try {
          const recoveredItem = await getChallengeCatalogItem(item!.id);
          if (!isCurrentRequest()) return;
          const participationId = positiveParticipationId(recoveredItem.participation_id);
          if (participationId !== null && !recoveredItem.can_join && participationId !== item!.participation_id) {
            navigate(`/challenges/participations/${participationId}`, { replace: Boolean(item!.participation_id) });
            return;
          }
          setItem(recoveredItem);
        } catch {
          if (!isCurrentRequest()) return;
        }
      }
      setRejoinOpen(false);
      setJoinError(reason instanceof Error ? reason.message : '챌린지에 참여하지 못했어요.');
    } finally {
      if (isCurrentRequest()) {
        joinRequestRef.current = null;
        setPending(false);
      }
    }
  }

  return (
    <>
    <Header title={item.name} onBack={goBack} className="h-auto! min-h-header py-2 [&_button]:shrink-0 [&_h1]:overflow-visible [&_h1]:whitespace-normal [&_h1]:break-words [&_h1]:[overflow-wrap:anywhere]" />
    <main className="flex flex-col gap-4 px-page-x py-5">
      <span className="self-start rounded-pill bg-primary-bg px-2 py-1 text-micro font-bold text-primary">공식</span>

      <section className="flex flex-col gap-2 rounded-card bg-primary-bg p-5" aria-labelledby="official-highlight-title">
        {item.reward_badge ? (
          <span className="flex size-14 overflow-hidden rounded-pill bg-card grayscale">
            <img src={apiAssetUrl(item.reward_badge.image_path)} alt={item.reward_badge.name} className="size-full object-contain" />
          </span>
        ) : null}
        <h2 id="official-highlight-title" className="break-words text-base font-bold [overflow-wrap:anywhere]">{item.reward_badge?.name ?? item.phrase}</h2>
        {item.reward_badge ? <p className="break-words text-sm text-primary [overflow-wrap:anywhere]">{item.phrase}</p> : null}
      </section>

      <section className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card" aria-labelledby="participation-guide-title">
        <h2 id="participation-guide-title" className="text-base font-bold">참여 안내</h2>
        <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
          <dt className="text-muted-foreground">모집기간</dt>
          <dd className="break-keep">{koreanChallengeDate(item.recruit_start_at)} ~ {koreanChallengeDate(item.recruit_end_at)}</dd>
          <dt className="text-muted-foreground">수행 기간</dt>
          <dd>참여 당일부터 {item.duration_days}일</dd>
          <dt className="text-muted-foreground">목표</dt>
          <dd>{targetLabel(item)}</dd>
          <dt className="text-muted-foreground">인증 방식</dt>
          <dd>{selfCheck ? '직접 인증' : '관리자 확인'}</dd>
        </dl>
        {!selfCheck ? <p className="rounded-input bg-muted-bg p-3 text-caption leading-5 text-muted-foreground">관리자 확인 방식은 현재 앱에서 참여할 수 없어요.</p> : null}
        {item.description ? <p className="break-words text-sm text-muted-foreground [overflow-wrap:anywhere]">{item.description}</p> : null}
      </section>

      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="certification-guide-title">
        <details key={item.id} className="group">
          <summary className="flex min-h-touch cursor-pointer list-none items-center justify-between gap-3 [&::-webkit-details-marker]:hidden">
            <h2 id="certification-guide-title" className="text-base font-bold">배지와 인증 안내</h2>
            <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-muted-foreground group-open:rotate-180" />
          </summary>
          <div className="mt-2 flex flex-col gap-2 text-caption leading-5 text-muted-foreground">
            {selfCheck ? <p>내가 누른 인증 기록을 기준으로 해요.</p> : null}
            <p>운동량·건강 상태를 검증하는 배지는 아니에요.</p>
          </div>
        </details>
      </section>

      {joinError ? <p role="alert" className="text-sm text-danger-strong">{joinError}</p> : null}
      <Button
        disabled={pending || (!item.participation_id && !canJoin)}
        onClick={() => canJoin
          ? item.participation_id ? setRejoinOpen(true) : void join()
          : item.participation_id && navigate(`/challenges/participations/${item.participation_id}`)}
      >
        {canJoin
          ? pending ? '참여 중' : item.participation_id ? '다시 참여하기' : '참여하기'
          : item.participation_id
            ? '진행 보기'
            : !selfCheck
              ? '현재 앱에서는 참여할 수 없어요'
              : '지금은 참여할 수 없어요'}
      </Button>
      <OfficialChallengeRejoinDialog open={rejoinOpen} pending={pending} onOpenChange={setRejoinOpen} onConfirm={() => void join()} />
    </main>
    </>
  );
}
