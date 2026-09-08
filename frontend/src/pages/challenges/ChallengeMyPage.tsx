import { useState } from 'react';
import { Link, useLocation } from 'react-router';

import { useChallengeMock } from '@/features/challenges';
import { ChallengeBadgeArt } from './ChallengeBadgeArt';
import { ChallengeProgressCard } from './ChallengeProgressCard';
import { ChallengePageHeading } from './ChallengePageHeading';

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
  const medication = participations.filter((item) => item.kind === 'medication');
  const awardCount = badges.reduce((sum, badge) => sum + (badge.awards?.length ?? (badge.earnedAt ? 1 : 0)), 0);

  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <ChallengePageHeading />
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
          <span>모은 배지 {earnedBadges.length}종 · {awardCount}회 획득</span>
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
        <div className="flex flex-col gap-1">
          <h3 className="text-base font-bold">복약 챌린지 · 처방별 진행</h3>
          <p className="text-caption text-muted-foreground">진행 중 {medication.filter((item) => item.status === 'active').length}개 · 달성 {medication.filter((item) => item.status === 'achieved').length}개</p>
          <p className="text-caption text-muted-foreground">각 처방을 달성할 때마다 같은 배지를 받아요. 달성한 처방은 지난 기록에서 볼 수 있어요.</p>
        </div>
        {active.filter((item) => item.kind === 'medication').map((participation) => (
          <ChallengeProgressCard key={participation.id} participation={participation} href={`${base}/participations/${participation.id}`} />
        ))}
        <h3 className="mt-2 text-base font-bold">다른 챌린지</h3>
        {active.filter((item) => item.kind !== 'medication').map((participation) => {
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
