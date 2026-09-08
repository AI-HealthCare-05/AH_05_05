import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  getCustomChallengeRecommendations,
  joinCustomChallenge,
  type CustomChallengeParticipation,
  type CustomChallengeRecommendation,
} from '@/entities/custom-challenge';
import { ApiError, getAuthGeneration } from '@/shared/api/client';
import { Button, Card, Header } from '@/shared/ui';

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
  const [successful, setSuccessful] = useState<Map<number, CustomChallengeParticipation>>(() => new Map());
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
    setSuccessful(new Map());
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

    const requestedIds = [...new Set(selectedIds)].sort((left, right) => left - right);
    const completed = new Map(successful);
    let firstError: string | null = null;
    for (const targetId of requestedIds) {
      if (completed.has(targetId)) continue;
      if (!isCurrent()) break;
      const idempotencyKey = medicationKeysRef.current.get(targetId) ?? crypto.randomUUID();
      medicationKeysRef.current.set(targetId, idempotencyKey);
      try {
        const result = await joinCustomChallenge(recommendation.templateId, {
          targetIds: [targetId],
          idempotencyKey,
        });
        if (!isCurrent()) break;
        medicationKeysRef.current.delete(targetId);
        completed.set(targetId, result);
        setSuccessful(new Map(completed));
      } catch (reason) {
        if (!isCurrent() || (reason instanceof ApiError && reason.status === 401)) break;
        if (!firstError) firstError = reason instanceof Error ? reason.message : '맞춤 챌린지에 참여하지 못했어요.';
        if (reason instanceof ApiError && reason.status === 403) break;
      }
    }
    if (isCurrent()) {
      setSuccessful(new Map(completed));
      if (firstError) setActionError(firstError);
      else if (requestedIds.every(id => completed.has(id))) {
        const only = requestedIds.length === 1 ? completed.get(requestedIds[0]) : null;
        navigate(only ? `/challenges/custom-participations/${only.id}` : '/challenges');
      }
      pendingRef.current = false;
      setPending(false);
    }
  }

  return (
    <>
      <Header title={recommendation?.challengeName ?? '맞춤 챌린지'} onBack={() => navigate('/challenges/tailored')} />
      <main className="flex min-h-full flex-col gap-4 px-page-x py-5">
      <p className="text-sm text-muted-foreground">참여할 기록을 선택해주세요</p>

      {!recommendation && !loadError ? <div role="status" aria-label="참여 대상 불러오는 중" className="min-h-72 animate-pulse rounded-card bg-muted-bg" /> : null}
      {loadError ? (
        <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <Button variant="secondary" onClick={() => setReloadKey(value => value + 1)}>다시 불러오기</Button>
        </div>
      ) : null}
      {recommendation ? (
        <Card className="gap-3 p-5 shadow-none">
          <h2 className="text-base font-bold">참여 대상</h2>
          {recommendation.targets.length === 0 ? <p className="text-sm text-muted-foreground">참여할 수 있는 기록이 없어요.</p> : null}
          <div className="flex flex-col gap-2">
            {recommendation.targets.map(target => {
              const alreadyMedication = supportedKind === 'medication' && target.existingParticipationId !== null;
              const done = successful.has(target.id);
              return (
                <label key={target.id} className="flex min-h-touch items-start gap-3 rounded-input bg-muted-bg p-3 text-sm">
                  <input
                    type="checkbox"
                    aria-label={`${target.name} 선택`}
                    checked={selectedIds.includes(target.id)}
                    disabled={alreadyMedication || done || pending}
                    onChange={event => setSelectedIds(current => event.target.checked
                      ? [...new Set([...current, target.id])]
                      : current.filter(id => id !== target.id))}
                    className="mt-0.5 size-5 accent-primary"
                  />
                  <span>
                    <strong className="block text-foreground">{target.name}</strong>
                    {done ? <span className="text-xs font-bold text-primary">{target.name} 참여 완료</span> : null}
                    {alreadyMedication ? (
                      <Link to={`/challenges/custom-participations/${target.existingParticipationId}`} className="block text-xs font-bold text-primary">
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
          <p className="text-sm text-muted-foreground">선택 대상: {selectedNames.length ? selectedNames.join(' · ') : '없음'}</p>
          <p className="text-xs leading-5 text-muted-foreground">홈에서 남긴 복용 기록이 진행률에 자동으로 반영돼요.</p>
        </Card>
      ) : null}

      {actionError ? <p role="alert" className="text-sm text-danger-strong">{actionError}</p> : null}
      {recommendation ? (
        <Button disabled={pending || selectedIds.length === 0} onClick={() => void submit()}>
          {pending
            ? '참여 처리 중'
            : actionError && successful.size > 0
              ? '실패한 대상 다시 시도'
              : actionError
                ? '다시 시도'
              : supportedKind === 'supplement'
                ? '선택한 영양제로 참여하기'
                : '선택한 대상으로 참여하기'}
        </Button>
      ) : null}
      <Link to="/challenges/tailored" className="min-h-touch py-3 text-center text-sm font-bold text-primary">맞춤 챌린지로 돌아가기</Link>
      </main>
    </>
  );
}
