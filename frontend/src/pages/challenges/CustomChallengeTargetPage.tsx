import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router';
import { ArrowLeft, ChevronDown } from 'lucide-react';

import { useSession } from '@/app/SessionContext';
import {
  getCustomChallengeRecommendations,
  joinCustomChallenge,
  type CustomChallengeRecommendation,
} from '@/entities/custom-challenge';
import { ApiError, getAuthGeneration } from '@/shared/api/client';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { Button } from '@/shared/ui';

type SupportedKind = 'medication' | 'supplement';

function expectedType(kind: SupportedKind) {
  return kind === 'medication' ? 'MEDICATION' : 'SUPPLEMENT';
}

function positiveId(value: string | null): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

export function CustomChallengeTargetPage() {
  const { kind } = useParams();
  const [searchParams] = useSearchParams();
  const templateId = positiveId(searchParams.get('templateId'));
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const generationRef = useRef(0);
  const pendingRef = useRef(false);
  const medicationKeysRef = useRef(new Map<number, string>());
  const supplementKeysRef = useRef(new Map<string, string>());
  const [recommendation, setRecommendation] = useState<CustomChallengeRecommendation | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [joinedMedicationIds, setJoinedMedicationIds] = useState<Record<number, number>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  principalRef.current = principalKey;

  const supportedKind: SupportedKind | null = kind === 'medication' || kind === 'supplement' ? kind : null;

  useEffect(() => {
    if (!supportedKind || templateId === null) return;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const requestPrincipal = principalKey;
    setRecommendation(null);
    setSelectedIds([]);
    setJoinedMedicationIds({});
    setLoadError(null);
    setActionError(null);
    pendingRef.current = false;
    setPending(false);
    medicationKeysRef.current.clear();
    supplementKeysRef.current.clear();
    getCustomChallengeRecommendations()
      .then(result => {
        if (generationRef.current !== generation || principalRef.current !== requestPrincipal) return;
        const selected = result.items.find(item => (
          item.templateId === templateId && item.challengeType === expectedType(supportedKind)
        ));
        if (!selected) {
          setLoadError('선택한 맞춤 챌린지를 찾을 수 없어요.');
          return;
        }
        setRecommendation(selected);
      })
      .catch((reason: unknown) => {
        if (generationRef.current !== generation || principalRef.current !== requestPrincipal) return;
        if (reason instanceof ApiError && reason.status === 401) return;
        setLoadError(reason instanceof Error ? reason.message : '참여 대상을 불러오지 못했어요.');
      });
    return () => {
      if (generationRef.current === generation) generationRef.current += 1;
    };
  }, [principalKey, reloadKey, supportedKind, templateId]);

  const selectedNames = useMemo(() => recommendation?.targets
    .filter(target => selectedIds.includes(target.id))
    .map(target => target.name) ?? [], [recommendation, selectedIds]);

  if (!supportedKind || templateId === null) {
    return <Navigate to="/challenges/tailored" replace />;
  }

  async function submit() {
    if (!recommendation || selectedIds.length === 0 || pendingRef.current) return;
    const requestPrincipal = principalKey;
    const requestGeneration = generationRef.current;
    const authGeneration = getAuthGeneration();
    const isCurrent = () => (
      principalRef.current === requestPrincipal
      && generationRef.current === requestGeneration
      && getAuthGeneration() === authGeneration
    );
    pendingRef.current = true;
    setPending(true);
    setActionError(null);

    if (supportedKind === 'supplement') {
      const targetIds = [...new Set(selectedIds)].sort((left, right) => left - right);
      const signature = targetIds.join(',');
      const idempotencyKey = supplementKeysRef.current.get(signature) ?? crypto.randomUUID();
      supplementKeysRef.current.set(signature, idempotencyKey);
      try {
        const result = await joinCustomChallenge(recommendation.templateId, { targetIds, idempotencyKey });
        if (!isCurrent()) return;
        supplementKeysRef.current.delete(signature);
        navigate(`/challenges/custom-participations/${result.id}`);
      } catch (reason) {
        if (!isCurrent() || (reason instanceof ApiError && reason.status === 401)) return;
        setActionError(reason instanceof Error ? reason.message : '맞춤 챌린지에 참여하지 못했어요.');
      } finally {
        if (principalRef.current === requestPrincipal && generationRef.current === requestGeneration) {
          pendingRef.current = false;
          setPending(false);
        }
      }
      return;
    }

    const targets = recommendation.targets.filter(target => (
      selectedIds.includes(target.id)
      && target.existingParticipationId === null
      && !joinedMedicationIds[target.id]
    ));
    const joined = { ...joinedMedicationIds };
    const failures: Array<{ id: number; message: string }> = [];
    try {
      for (const target of targets) {
        if (!isCurrent()) return;
        const idempotencyKey = medicationKeysRef.current.get(target.id) ?? crypto.randomUUID();
        medicationKeysRef.current.set(target.id, idempotencyKey);
        try {
          const result = await joinCustomChallenge(recommendation.templateId, {
            targetIds: [target.id],
            idempotencyKey,
          });
          if (!isCurrent()) return;
          medicationKeysRef.current.delete(target.id);
          joined[target.id] = result.id;
        } catch (reason) {
          if (!isCurrent() || (reason instanceof ApiError && reason.status === 401)) return;
          const message = reason instanceof Error ? reason.message : '맞춤 챌린지에 참여하지 못했어요.';
          failures.push({ id: target.id, message: `${target.name}: ${message}` });
        }
      }
      setJoinedMedicationIds(joined);
      setSelectedIds(failures.map(failure => failure.id));
      if (failures.length > 0) {
        setActionError(`${failures.map(failure => failure.message).join('\n')}\n실패한 처방만 다시 시도해주세요.`);
        return;
      }
      const participationIds = Object.values(joined);
      if (participationIds.length > 0) {
        navigate(participationIds.length === 1
          ? `/challenges/custom-participations/${participationIds[0]}`
          : '/challenges');
      }
    } finally {
      if (principalRef.current === requestPrincipal && generationRef.current === requestGeneration) {
        pendingRef.current = false;
        setPending(false);
      }
    }
  }

  return (
    <>
      <header className="flex items-center gap-3 px-page-x pt-5">
        <button type="button" aria-label="뒤로 가기" onClick={() => navigate('/challenges/tailored')} className="flex size-11 shrink-0 items-center justify-center rounded-pill">
          <ArrowLeft aria-hidden="true" className="size-5" />
        </button>
        <div className="min-w-0">
          <h1 className="break-words text-[22px] font-bold leading-7 [overflow-wrap:anywhere]">{recommendation?.challengeName ?? '맞춤 챌린지'}</h1>
          <p className="text-caption text-muted-foreground">맞춤 챌린지</p>
        </div>
      </header>
      <main className="flex flex-col gap-4 px-page-x py-5">

      {!recommendation && !loadError ? <div role="status" aria-label="참여 대상 불러오는 중" className="min-h-72 animate-pulse rounded-card bg-muted-bg" /> : null}
      {loadError ? (
        <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <Button variant="secondary" onClick={() => setReloadKey(value => value + 1)}>다시 불러오기</Button>
        </div>
      ) : null}
      {recommendation ? (
        <>
        <section className="flex flex-col gap-2 rounded-card bg-primary-bg p-5" aria-labelledby="custom-highlight-title">
          {recommendation.rewardBadge ? <span className="flex size-14 overflow-hidden rounded-pill bg-card grayscale">
            <img src={apiAssetUrl(recommendation.rewardBadge.imagePath)} alt={recommendation.rewardBadge.name} className="size-full object-contain" />
          </span> : null}
          <h2 id="custom-highlight-title" className="break-words text-base font-bold [overflow-wrap:anywhere]">{recommendation.rewardBadge?.name ?? recommendation.challengeName}</h2>
          <p className="break-words text-sm text-primary [overflow-wrap:anywhere]">{recommendation.rewardBadge?.description || (supportedKind === 'medication' ? '처방 일정에 맞춰 복약 기록 남기기' : '매일 꾸준히 영양제 기록 남기기')}</p>
        </section>
        <section className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card" aria-labelledby="custom-participation-guide-title">
          <h2 id="custom-participation-guide-title" className="text-base font-bold">참여 안내</h2>
          <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
            <dt className="text-muted-foreground">수행 기간</dt>
            <dd>{supportedKind === 'medication' ? '참여 시점부터 처방 종료일까지' : '참여일 포함 7일'}</dd>
            <dt className="text-muted-foreground">목표</dt>
            <dd>예정된 복용 기록 모두 남기기</dd>
            <dt className="text-muted-foreground">인증 방식</dt>
            <dd>복용 기록 자동 연동</dd>
          </dl>
          {supportedKind === 'medication' ? <p className="rounded-input bg-muted-bg p-3 text-caption leading-5 text-muted-foreground">여러 처방을 선택할 수 있어요. 처방별로 각각 참여하며, 남은 복약 일정 전체가 목표 기간이 돼요.</p> : null}
        </section>
        <section className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card" aria-labelledby="custom-join-target-title">
          <h2 id="custom-join-target-title" className="text-base font-bold">참여 대상</h2>
          <p className="text-caption text-muted-foreground">참여할 기록을 선택해주세요</p>
          {recommendation.targets.length === 0 ? <p className="text-sm text-muted-foreground">참여할 수 있는 기록이 없어요.</p> : null}
          <div className="flex flex-col gap-2">
            {recommendation.targets.map(target => {
              const existingParticipationId = joinedMedicationIds[target.id] ?? target.existingParticipationId;
              const alreadyMedication = supportedKind === 'medication' && existingParticipationId !== null;
              return (
                <label key={target.id} className="flex min-h-touch items-start gap-3 rounded-input bg-muted-bg p-3 text-sm">
                  <input
                    type="checkbox"
                    aria-label={`${target.name} 선택`}
                    checked={selectedIds.includes(target.id)}
                    disabled={alreadyMedication || pending}
                    onChange={event => {
                      const checked = event.target.checked;
                      setActionError(null);
                      setSelectedIds(current => checked
                        ? [...new Set([...current, target.id])]
                        : current.filter(id => id !== target.id));
                    }}
                    className="mt-0.5 size-5 shrink-0 accent-primary"
                  />
                  <span className="min-w-0 break-words [overflow-wrap:anywhere]">
                    <strong className="block text-foreground">{target.name}</strong>
                    {alreadyMedication ? (
                      <Link to={`/challenges/custom-participations/${existingParticipationId}`} className="block text-xs font-bold text-primary">
                        이미 참여 중인 처방 보기 ›
                      </Link>
                    ) : null}
                    {supportedKind === 'supplement' && target.existingParticipationId !== null
                      ? <span className="text-xs text-muted-foreground">이 영양제가 포함된 참여 기록이 있어요</span>
                      : null}
                  </span>
                </label>
              );
            })}
          </div>
          <div className="text-caption text-muted-foreground">
            <p>선택 대상: {selectedNames.length ? `${selectedNames.length}개` : '없음'}</p>
            {selectedNames.length ? <ul aria-label="선택 대상" className="mt-2 flex flex-col gap-2">
              {selectedNames.map((name, index) => <li key={index} className="break-words [overflow-wrap:anywhere]">{name}</li>)}
            </ul> : null}
          </div>
        </section>
        <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="custom-certification-guide-title">
          <details key={recommendation.templateId} className="group">
            <summary className="flex min-h-touch cursor-pointer list-none items-center justify-between gap-3 [&::-webkit-details-marker]:hidden">
              <h2 id="custom-certification-guide-title" className="text-base font-bold">배지와 인증 안내</h2>
              <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-muted-foreground group-open:rotate-180" />
            </summary>
            <div className="mt-2 flex flex-col gap-2 text-caption leading-5 text-muted-foreground">
              <p>홈에서 남긴 복용 기록이 진행률에 자동으로 반영돼요.</p>
              <p>{recommendation.rewardBadge ? '전체 목표를 완료한 뒤 챌린지 상세를 열면 배지를 받아요. 지급 후에는 결과와 배지가 유지돼요.' : '현재 이 챌린지에 등록된 배지가 없어요.'}</p>
              <p>복용 효과나 건강 상태를 검증하는 배지는 아니에요.</p>
            </div>
          </details>
        </section>
        </>
      ) : null}

      {Object.keys(joinedMedicationIds).length > 0 ? (
        <p role="status" className="text-sm font-bold text-primary">처방 {Object.keys(joinedMedicationIds).length}개 참여 완료. 완료된 참여는 유지돼요.</p>
      ) : null}
      {actionError ? <p role="alert" className="whitespace-pre-line break-words text-sm text-danger-strong">{actionError}</p> : null}
      {recommendation ? (
        <Button disabled={pending || selectedIds.length === 0} onClick={() => void submit()}>
          {pending
            ? '참여 처리 중'
            : actionError
              ? '다시 시도'
              : supportedKind === 'supplement'
                ? '선택한 영양제로 참여하기'
                : '선택한 처방으로 참여하기'}
        </Button>
      ) : null}
      <Link to="/challenges/tailored" className="min-h-touch py-3 text-center text-sm font-bold text-primary">맞춤 챌린지로 돌아가기</Link>
      </main>
    </>
  );
}
