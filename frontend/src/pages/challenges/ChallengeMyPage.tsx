import { useState } from 'react';
import { Link, useLocation } from 'react-router';

import { useChallengeMock } from '@/features/challenges';
import { ChallengeBadgeArt } from './ChallengeBadgeArt';
import { ChallengeProgressCard } from './ChallengeProgressCard';

function challengeBase(pathname: string) {
  return pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
}

export function ChallengeMyPage() {
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const location = useLocation();
  const base = challengeBase(location.pathname);
  const { badges, definitions, participations, demoToday, checkIn } = useChallengeMock();
  const active = participations.filter((participation) => participation.status === 'active');
  const history = participations.filter((participation) => participation.status !== 'active');
  const earnedBadges = badges.filter((badge) => badge.earnedAt);

  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <h1 className="text-[22px] font-bold leading-6 text-foreground">챌린지</h1>
      <nav aria-label="챌린지 보기" className="grid h-11 grid-cols-2 rounded-input bg-muted-bg p-1">
        <Link aria-current="page" to={base} className="flex items-center justify-center rounded-[9px] bg-card text-sm font-bold text-primary shadow-card">
          마이
        </Link>
        <Link to={`${base}/browse`} className="flex items-center justify-center rounded-[9px] text-sm font-medium text-muted-foreground">
          둘러보기
        </Link>
      </nav>

      <section className="flex flex-col gap-3 rounded-card bg-primary-bg p-5" aria-labelledby="badge-summary-title">
        <h2 id="badge-summary-title" className="text-base font-bold">작은 실천이 쌓이고 있어요</h2>
        <div className="flex items-center justify-between text-caption text-primary">
          <span>모은 배지 {earnedBadges.length}개</span>
          <Link to={`${base}/badges`} className="font-bold">전체 보기 ›</Link>
        </div>
        <div className="flex gap-3 text-primary" aria-label="최근 획득 배지">
          {earnedBadges.slice(0, 3).map((badge) => (
            <ChallengeBadgeArt key={badge.id} badge={badge} className="size-9" />
          ))}
        </div>
      </section>

      <section aria-labelledby="active-challenges-title" className="flex flex-col gap-3">
        <h2 id="active-challenges-title" className="sr-only">진행 중인 챌린지</h2>
        {active.map((participation) => {
          const definition = definitions.find((item) => item.id === participation.challengeId);
          return (
            <ChallengeProgressCard
              key={participation.id}
              participation={participation}
              href={`${base}/participations/${participation.id}`}
              onCheckIn={() => checkIn(participation.id)}
              checkInDisabled={participation.startDate > demoToday}
              unitLabel={definition?.frequency.type === 'weekly' ? '회 인증' : undefined}
            />
          );
        })}
      </section>

      {history.length > 0 ? (
        <section aria-labelledby="challenge-history-title" className="flex flex-col gap-3">
          <div className="flex min-h-touch items-center justify-between gap-3">
            <h2 id="challenge-history-title" className="text-base font-bold">지난 기록</h2>
            <button
              type="button"
              aria-expanded={historyExpanded}
              aria-controls="challenge-history-list"
              aria-label={historyExpanded ? '지난 기록 접기' : '지난 기록 펼치기'}
              onClick={() => setHistoryExpanded((current) => !current)}
              className="min-h-touch rounded-pill px-3 text-sm font-bold text-primary"
            >
              {historyExpanded ? '접기' : `${history.length}개 보기`}
            </button>
          </div>
          {historyExpanded ? (
            <div id="challenge-history-list" className="flex flex-col gap-3">
              {history.map((participation) => (
                <ChallengeProgressCard
                  key={participation.id}
                  participation={participation}
                  href={`${base}/participations/${participation.id}`}
                  unitLabel={definitions.find((item) => item.id === participation.challengeId)?.frequency.type === 'weekly' ? '회 인증' : undefined}
                />
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
