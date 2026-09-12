import { ArrowRight } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { useSession } from '@/app/SessionContext';
import {
  getCustomChallengeRecommendations,
  type CustomChallengeRecommendation,
} from '@/entities/custom-challenge';
import { ApiError } from '@/shared/api/client';
import { Button, Card, Header } from '@/shared/ui';
import { LoadingState } from '@/shared/ui/LoadingState';

function kindPath(type: CustomChallengeRecommendation['challengeType']) {
  if (type === 'MEDICATION') return 'medication';
  if (type === 'SUPPLEMENT') return 'supplement';
  return null;
}

export function CustomChallengeRecommendationsPage() {
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const principalRef = useRef(principalKey);
  const generationRef = useRef(0);
  const [items, setItems] = useState<CustomChallengeRecommendation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  principalRef.current = principalKey;

  useEffect(() => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const requestPrincipal = principalKey;
    setItems(null);
    setError(null);
    getCustomChallengeRecommendations()
      .then(result => {
        if (generationRef.current === generation && principalRef.current === requestPrincipal) {
          setItems(result.items.filter(item => kindPath(item.challengeType) !== null));
        }
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
    <>
      <Header title="맞춤 챌린지" onBack={() => navigate('/challenges/browse')} />
      <main className="flex min-h-full flex-col gap-4 px-page-x py-5">
      <p className="text-sm text-muted-foreground">등록한 기록에 맞는 챌린지를 확인해보세요</p>

      {items === null && !error ? (
        <LoadingState label="맞춤 챌린지 불러오는 중">맞춤 챌린지를 불러오고 있어요.</LoadingState>
      ) : null}
      {error ? (
        <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button variant="secondary" onClick={() => setReloadKey(value => value + 1)}>다시 불러오기</Button>
        </div>
      ) : null}
      {items?.length === 0 ? (
        <Card className="gap-3 p-5 shadow-none">
          <h2 className="text-base font-bold">지금 참여할 수 있는 맞춤 챌린지가 없어요.</h2>
          <p className="text-sm text-muted-foreground">복약 또는 영양제 기록을 등록한 뒤 다시 확인해주세요.</p>
          <Link to="/medications" className="text-sm font-bold text-primary">내 기록 확인하기 ›</Link>
        </Card>
      ) : null}
      {items?.map(item => {
        const kind = kindPath(item.challengeType);
        if (!kind) return null;
        const available = item.targets.filter(target => target.existingParticipationId === null).length;
        return (
          <Link
            key={item.templateId}
            to={`/challenges/tailored/${kind}?templateId=${item.templateId}`}
            className="block"
            aria-label={`${item.challengeName} 대상 선택`}
          >
            <Card className="gap-2 p-5 shadow-none">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-base font-bold text-foreground">{item.challengeName}</h2>
                <ArrowRight aria-hidden className="size-5 shrink-0 text-primary" />
              </div>
              <p className="text-xs font-bold text-primary">
                {item.challengeType === 'MEDICATION' ? '복약 기록 연동' : '영양제 기록 연동'}
              </p>
              <p className="text-sm text-muted-foreground">참여 가능한 대상 {available}개</p>
            </Card>
          </Link>
        );
      })}

      </main>
    </>
  );
}
