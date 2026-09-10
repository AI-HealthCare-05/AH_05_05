import { useEffect, useState } from 'react';
import { DrawnChevron } from '@/shared/ui/DrawnArrow';
import { Link, useParams } from 'react-router';

import { useSession } from '@/app/SessionContext';
import { getChallengeCatalog, getUserChallengeBadges } from '@/entities/challenge';
import { Button } from '@/shared/ui/Button';
import { LoadingState } from '@/shared/ui/LoadingState';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { officialBadgeViews, type OfficialBadgeView } from './officialBadgeViews';

function positiveId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

async function loadBadge(id: number) {
  const [catalog, badges] = await Promise.all([getChallengeCatalog(), getUserChallengeBadges()]);
  return officialBadgeViews(catalog.items, badges.items).find(item => item.id === id) ?? null;
}

export function OfficialChallengeBadgePage() {
  const id = positiveId(useParams().badgeId);
  const { principalKey } = useSession();
  const [badge, setBadge] = useState<OfficialBadgeView | null>(null);
  const [loaded, setLoaded] = useState(id === null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (id === null) return;
    let active = true;
    setBadge(null);
    setLoaded(false);
    setError(null);
    loadBadge(id)
      .then(result => {
        if (!active) return;
        setBadge(result);
        setLoaded(true);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : '배지를 불러오지 못했어요.');
        setLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [id, principalKey, reloadKey]);

  if (error) {
    return <main className="flex flex-col gap-4 px-page-x py-5"><h1 className="text-[22px] font-bold">배지 상세</h1><p role="alert" className="text-sm text-muted-foreground">{error}</p><Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button></main>;
  }
  if (!loaded) return <main className="px-page-x py-5"><LoadingState label="배지 상세 불러오는 중">배지를 불러오고 있어요.</LoadingState></main>;
  if (!badge) return <main className="flex flex-col gap-4 px-page-x py-5"><h1 className="text-[22px] font-bold">배지를 찾을 수 없어요</h1><Link to="/challenges/badges" className="font-bold text-primary">내 배지로 돌아가기</Link></main>;

  const earned = badge.awards.length > 0;
  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
      <h1 className="text-[22px] font-bold leading-8 text-foreground">배지 상세</h1>
      <p className="text-sm text-muted-foreground">{badge.official ? '공식 챌린지 달성' : '챌린지 달성'}</p>
      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="badge-name">
        <img src={apiAssetUrl(badge.imagePath)} alt={badge.name} className={`size-20 rounded-pill object-contain ${earned ? '' : 'grayscale opacity-60'}`} />
        <h2 id="badge-name" className="text-base font-bold text-foreground">{badge.name}</h2>
        <p className="text-xs text-primary">{badge.official ? '공식 챌린지 배지' : '챌린지 배지'}</p>
        <p className="whitespace-pre-line text-sm text-muted-foreground">{earned ? `총 ${badge.awards.length}회 획득` : '아직 획득하지 않았어요.'}{badge.description ? `\n${badge.description}` : ''}</p>
      </section>
      {earned ? (
        <section className="rounded-card bg-card p-5 shadow-card" aria-labelledby="badge-awards-title"><h2 id="badge-awards-title" className="mb-3 text-base font-bold">획득 이력</h2><ul aria-label="배지 획득 이력" className="divide-y divide-border">{badge.awards.map(award => <li key={award.id}><Link to={`/challenges/participations/${award.user_challenge_id}`} className="flex min-h-touch flex-col gap-1 py-3"><span className="text-sm font-bold text-foreground">{award.badge_name} <DrawnChevron direction="right" className="inline size-3.5 align-middle" /></span><span className="text-caption text-muted-foreground">{award.awarded_at.slice(0, 10)} 획득 · 1회</span></Link></li>)}</ul></section>
      ) : null}
      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="badge-rule"><h2 id="badge-rule" className="text-base font-bold text-foreground">배지 지급 기준</h2><p className="text-sm leading-6 text-muted-foreground">서버에 승인된 챌린지 달성 기록을 기준으로 지급 상태를 보여드려요.</p></section>
      <Link to="/challenges/badges" className="font-bold text-primary">내 배지로 돌아가기</Link>
    </main>
  );
}
