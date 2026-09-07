import { Award } from 'lucide-react';
import { Link, useLocation } from 'react-router';
import { useChallengeMock } from '@/features/challenges';
import type { ChallengeBadge } from '@/features/challenges/types';
import { ChallengeBadgeArt } from './ChallengeBadgeArt';

interface ChallengeBadgesPageProps {
  badgesOverride?: ChallengeBadge[];
}

export function ChallengeBadgesPage({ badgesOverride }: ChallengeBadgesPageProps) {
  const { badges } = useChallengeMock();
  const location = useLocation();
  const base = location.pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const visibleBadges = badgesOverride ?? badges;
  const earnedCount = visibleBadges.filter((badge) => badge.earnedAt).length;

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
      <h1 className="text-[22px] font-bold leading-8 text-foreground">내 배지</h1>
      <p className="text-sm text-muted-foreground">모은 배지 {earnedCount}개</p>

      {visibleBadges.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center gap-4 rounded-card bg-card p-5 text-center shadow-card">
          <Award aria-hidden className="size-11 text-disabled-foreground" />
          <div>
            <p className="font-bold text-foreground">아직 모은 배지가 없어요</p>
            <p className="mt-1 text-sm text-muted-foreground">챌린지를 달성하면 배지가 여기에 모여요.</p>
          </div>
          <Link to={`${base}/browse`} className="font-bold text-primary">
            챌린지 둘러보기
          </Link>
        </div>
      ) : (
        <ul aria-label="챌린지 배지" className="grid grid-cols-2 gap-4">
          {visibleBadges.map((badge) => {
            const earned = Boolean(badge.earnedAt);
            return (
              <li key={badge.id}>
                <Link
                  to={`${base}/badges/${badge.id}`}
                  aria-label={`${badge.name}, ${earned ? '획득' : '미획득'}`}
                  className="flex h-40 flex-col gap-2.5 rounded-card bg-card p-4 shadow-card"
                >
                  <ChallengeBadgeArt badge={badge} />
                  <span className="line-clamp-2 text-sm font-bold text-foreground">{badge.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {earned ? '획득' : '미획득'}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
