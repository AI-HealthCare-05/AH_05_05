import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { useSession } from '@/app/SessionContext';
import { getCustomChallengeBadges, getCustomChallengeParticipations } from '@/entities/custom-challenge';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { navigateBackOrReplace } from '@/shared/lib/navigation';
import { Button } from '@/shared/ui/Button';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { Header } from '@/shared/ui/Header';
import { LoadingState } from '@/shared/ui/LoadingState';
import { customChallengeDateLabel } from './customChallengeDates';
import { customBadgeViews } from './customBadgeViews';

async function loadBadge(id: number) {
  const [badges, participations] = await Promise.all([
    getCustomChallengeBadges(), getCustomChallengeParticipations(),
  ]);
  const badge = customBadgeViews(badges).find(item => item.badgeId === id);
  if (!badge) return null;
  const participationById = new Map(participations.items.map(item => [item.id, item]));
  const awards = badge.awards
    .map(award => ({ ...award, participation: participationById.get(award.participationId) }));
  return { ...badge, awards };
}

export function CustomChallengeBadgePage() {
  const { badgeId } = useParams();
  const id = badgeId && /^[1-9]\d*$/.test(badgeId) && Number.isSafeInteger(Number(badgeId))
    ? Number(badgeId) : null;
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = JSON.stringify([id, principalKey, reloadKey]);
  const [result, setResult] = useState<{
    key: string; badge: Awaited<ReturnType<typeof loadBadge>>; error: string | null;
  } | null>(null);
  const goBack = () => navigateBackOrReplace(navigate, '/challenges/badges');

  useEffect(() => {
    if (id === null) return;
    let active = true;
    loadBadge(id).then(badge => {
      if (active) setResult({ key: requestKey, badge, error: null });
    }).catch((reason: unknown) => {
      if (active) setResult({ key: requestKey, badge: null,
        error: reason instanceof Error ? reason.message : '배지를 불러오지 못했어요.' });
    });
    return () => { active = false; };
  }, [id, requestKey]);

  const current = result?.key === requestKey ? result : null;
  const badge = current?.badge;
  return (
    <>
      <Header title="배지 상세" onBack={goBack} />
      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
        {id !== null && !current ? (
          <LoadingState label="배지 상세 불러오는 중">배지를 불러오고 있어요.</LoadingState>
        ) : current?.error ? (
          <>
            <p role="alert" className="text-sm text-muted-foreground">{current.error}</p>
            <Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button>
          </>
        ) : !badge ? (
          <>
            <h1 className="text-[22px] font-bold">배지를 찾을 수 없어요</h1>
          </>
        ) : (
          <>
            <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="badge-name">
              <img src={apiAssetUrl(badge.imagePath)} alt={badge.name} className={`size-20 rounded-pill object-contain ${badge.awards.length ? '' : 'grayscale opacity-60'}`} />
              <h2 id="badge-name" className="text-base font-bold text-foreground">{badge.name}</h2>
              <p className="text-xs text-primary">맞춤 챌린지 배지</p>
              <p className="text-sm text-muted-foreground">{badge.awards.length ? `총 ${badge.awards.length}회 획득` : '아직 획득하지 않았어요.'}</p>
            </section>
            {badge.awards.length > 0 ? <section className="rounded-card bg-card p-5 shadow-card" aria-labelledby="badge-awards-title">
              <h2 id="badge-awards-title" className="mb-3 text-base font-bold">획득 이력</h2>
              <ul aria-label="배지 획득 이력" className="divide-y divide-border">
                {badge.awards.map(award => (
                  <li key={award.id}>
                    <Link to={`/challenges/custom-participations/${award.participationId}`} className="flex min-h-touch flex-col gap-1 break-words py-3">
                      <span className="flex items-center justify-between gap-3 text-sm font-bold text-foreground">
                        <span className="min-w-0">{award.participation?.challengeName ?? `챌린지 참여 #${award.participationId}`}</span>
                        <DrawnChevron direction="right" className="size-3.5 shrink-0" />
                      </span>
                      {award.participation?.targets.length ? <span className="text-sm text-muted-foreground">{award.participation.targets.map(target => target.name).join(', ')}</span> : null}
                      <span className="text-caption text-muted-foreground">{customChallengeDateLabel(award.awardedAt)} 획득 · 1회</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section> : null}
          </>
        )}
      </main>
    </>
  );
}
