import { Award } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { useSession } from '@/app/SessionContext';
import { getChallengeCatalog, getUserChallengeBadges } from '@/entities/challenge';
import { Button } from '@/shared/ui/Button';
import { Header } from '@/shared/ui/Header';
import { apiAssetUrl } from '@/shared/api/assetUrl';
import { officialBadgeViews, type OfficialBadgeView } from './officialBadgeViews';

async function loadBadges() {
  const [catalog, badges] = await Promise.all([getChallengeCatalog(), getUserChallengeBadges()]);
  return officialBadgeViews(catalog.items, badges.items);
}

export function OfficialChallengeBadgesPage() {
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const [badges, setBadges] = useState<OfficialBadgeView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  function goBack() {
    const index = window.history.state?.idx;
    if (typeof index === 'number' && index > 0) {
      navigate(-1);
      return;
    }
    navigate('/challenges', { replace: true });
  }

  useEffect(() => {
    let active = true;
    setBadges(null);
    setError(null);
    loadBadges()
      .then(result => {
        if (active) setBadges(result);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '배지를 불러오지 못했어요.');
      });
    return () => {
      active = false;
    };
  }, [principalKey, reloadKey]);

  if (error) {
    return (
      <>
        <Header title="내 배지" onBack={goBack} />
        <main className="flex flex-col gap-4 px-page-x py-5">
          <div role="alert" className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card"><p className="text-sm text-muted-foreground">{error}</p><Button variant="secondary" onClick={() => setReloadKey(key => key + 1)}>다시 불러오기</Button></div>
        </main>
      </>
    );
  }

  if (!badges) return <><Header title="내 배지" onBack={goBack} /><main role="status" aria-label="배지 불러오는 중" className="mx-page-x my-5 min-h-72 animate-pulse rounded-card bg-muted-bg" /></>;

  const earnedCount = badges.filter(item => item.awards.length > 0).length;
  const awardCount = badges.reduce((sum, item) => sum + item.awards.length, 0);

  return (
    <>
      <Header title="내 배지" onBack={goBack} />
      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
      <p className="text-sm text-muted-foreground">모은 배지 {earnedCount}종 · 총 {awardCount}회 획득</p>
      {badges.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center gap-4 rounded-card bg-card p-5 text-center shadow-card">
          <Award aria-hidden className="size-11 text-disabled-foreground" />
          <div><p className="font-bold text-foreground">아직 확인할 배지가 없어요</p><p className="mt-1 text-sm text-muted-foreground">배지가 있는 공식 챌린지를 둘러보세요.</p></div>
          <Link to="/challenges/browse" className="font-bold text-primary">챌린지 둘러보기</Link>
        </div>
      ) : (
        <ul aria-label="챌린지 배지" className="grid grid-cols-2 gap-4">
          {badges.map(item => {
            const earned = item.awards.length > 0;
            const label = earned ? `${item.awards.length}회 획득` : '미획득';
            return (
              <li key={item.id}>
                <Link to={`/challenges/badges/${item.id}`} aria-label={`${item.name}, ${label}`} className="flex min-h-40 flex-col gap-2.5 rounded-card bg-card p-4 shadow-card">
                  <img src={apiAssetUrl(item.imagePath)} alt={item.name} className={`size-11 rounded-pill object-contain ${earned ? '' : 'grayscale opacity-60'}`} />
                  <span className="line-clamp-2 text-sm font-bold text-foreground">{item.name}</span>
                  <span className="text-xs text-muted-foreground">{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      </main>
    </>
  );
}
