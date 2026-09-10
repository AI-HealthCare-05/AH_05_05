import { useEffect, useRef, useState } from 'react';

import { useSession } from '@/app/SessionContext';
import {
  getCustomChallengeParticipations,
  type CustomChallengeParticipation,
} from '@/entities/custom-challenge';
import { ApiError } from '@/shared/api/client';

export function useCustomChallengeMy() {
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

  return { items, error, reload: () => setReloadKey(value => value + 1) };
}
