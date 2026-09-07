import { Link, useLocation, useParams } from 'react-router';
import { useChallengeMock } from '@/features/challenges';
import { ChallengeBadgeArt } from './ChallengeBadgeArt';

export function ChallengeBadgePage() {
  const { badgeId } = useParams();
  const { badges, definitions, participations } = useChallengeMock();
  const location = useLocation();
  const base = location.pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const badge = badges.find((item) => item.id === badgeId);

  if (!badge) {
    return (
      <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
        <h1 className="text-[22px] font-bold leading-8 text-foreground">배지를 찾을 수 없어요</h1>
        <Link to={`${base}/badges`} className="font-bold text-primary">내 배지로 돌아가기</Link>
      </main>
    );
  }

  const participation = participations.find(
    (item) => item.badgeId === badge.id && item.status === 'achieved',
  );
  const isOfficial = definitions.some(
    (definition) => definition.badgeId === badge.id && definition.kind === 'official',
  );

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-page-x py-5">
      <h1 className="text-[22px] font-bold leading-8 text-foreground">배지 상세</h1>
      <p className="text-sm text-muted-foreground">{isOfficial ? '공식 챌린지 달성' : '챌린지 달성'}</p>

      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="badge-name">
        <ChallengeBadgeArt badge={badge} className="size-20" />
        <h2 id="badge-name" className="text-base font-bold text-foreground">{badge.name}</h2>
        <p className="text-xs text-primary">{isOfficial ? '공식 챌린지 배지' : '기본 챌린지 배지'}</p>
        <p className="whitespace-pre-line text-sm text-muted-foreground">
          {badge.earnedAt ? `${badge.earnedAt} 획득\n` : '아직 획득하지 않았어요.\n'}
          {participation ? `${participation.completed} / ${participation.target}회 기록` : badge.description}
        </p>
      </section>

      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="badge-rule">
        <h2 id="badge-rule" className="text-base font-bold text-foreground">배지 지급 기준</h2>
        <p className="text-xs text-primary">사용자 인증 기록</p>
        <p className="text-sm leading-6 text-muted-foreground">
          {badge.description}<br />
          RxVita에 남긴 기록에 따라 지급한 배지예요.<br />
          실제 운동량·건강 상태의 인증은 아니에요.
        </p>
      </section>

      <Link
        to={`${base}/badges`}
        className="flex min-h-control items-center justify-center rounded-button bg-primary px-4 text-sm font-bold text-white"
      >
        내 배지로 돌아가기
      </Link>
    </main>
  );
}
