import { DrawnArrow } from '@/shared/ui/DrawnArrow';
import { useLocation, useNavigate, useParams } from 'react-router';

import { useChallengeMock } from '@/features/challenges';
import { Button } from '@/shared/ui/Button';
import { ChallengeBadgeArt } from './ChallengeBadgeArt';

function challengeBase(pathname: string) {
  return pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
}

function shortDate(date: string) {
  const [, month, day] = date.split('-');
  return `${Number(month)}.${Number(day)}`;
}

export function OfficialChallengePage() {
  const { challengeId = '' } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const base = challengeBase(location.pathname);
  const { definitions, participations, badges, demoToday, joinChallenge } = useChallengeMock();
  const definition = definitions.find((item) => item.id === challengeId);

  if (!definition || definition.kind !== 'official') {
    return (
      <section className="flex flex-col gap-4">
        <h1 className="text-xl font-bold">챌린지를 찾을 수 없어요</h1>
        <Button variant="secondary" onClick={() => navigate(`${base}/browse`)}>둘러보기로 돌아가기</Button>
      </section>
    );
  }

  const participation = participations.find((item) => item.challengeId === definition.id);
  const badge = badges.find((item) => item.id === definition.badgeId);
  const enrollmentEnded = Boolean(definition.enrollmentEnd && definition.enrollmentEnd < demoToday);
  const enrollmentNotStarted = Boolean(definition.enrollmentStart && definition.enrollmentStart > demoToday);
  const cannotJoin = !participation && (enrollmentEnded || enrollmentNotStarted);
  const frequency = definition.frequency;
  const duration = frequency.type === 'daily' ? frequency.durationDays : frequency.durationWeeks * 7;
  const target = frequency.type === 'daily'
    ? frequency.durationDays
    : frequency.targetDaysPerWeek * frequency.durationWeeks;

  function join() {
    const participationId = joinChallenge(definition!.id);
    navigate(`${base}/participations/${participationId}`);
  }

  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <header className="flex items-center gap-3">
        <button type="button" aria-label="뒤로 가기" onClick={() => navigate(`${base}/browse`)} className="flex size-11 shrink-0 items-center justify-center rounded-pill">
          <DrawnArrow direction="left" className="size-5" />
        </button>
        <div className="min-w-0">
          <h1 className="truncate text-[22px] font-bold leading-7">{definition.title}</h1>
          <p className="text-caption text-muted-foreground">공식 챌린지</p>
        </div>
      </header>

      <section className="flex flex-col gap-2 rounded-card bg-primary-bg p-5" aria-labelledby="official-highlight-title">
        {badge ? <ChallengeBadgeArt badge={badge} className="size-14" /> : null}
        <h2 id="official-highlight-title" className="text-base font-bold">{badge?.name ?? '공식 배지'}</h2>
        <p className="text-sm text-primary">매일의 작은 실천을 배지로 남겨요</p>
      </section>

      <section className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card" aria-labelledby="participation-guide-title">
        <h2 id="participation-guide-title" className="text-base font-bold">참여 안내</h2>
        <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-2 text-sm">
          <dt className="text-muted-foreground">모집</dt>
          <dd>{definition.enrollmentStart && definition.enrollmentEnd ? `${shortDate(definition.enrollmentStart)} ~ ${shortDate(definition.enrollmentEnd)}` : '상시 참여'}</dd>
          <dt className="text-muted-foreground">수행 기간</dt>
          <dd>참여 당일부터 {duration}일</dd>
          <dt className="text-muted-foreground">목표</dt>
          <dd>{definition.taskLabel} · {frequency.type === 'daily' ? '매일' : `주 ${frequency.targetDaysPerWeek}회`}</dd>
        </dl>
        <p className="rounded-input bg-muted-bg p-3 text-caption text-muted-foreground">
          {frequency.type === 'daily'
            ? `참여한 날부터 기간이 시작되며 ${target}일 모두 인증하면 배지를 받아요.`
            : `${frequency.durationWeeks}주 동안 매주 ${frequency.targetDaysPerWeek}회 목표를 채우면 배지를 받아요.`}
        </p>
      </section>

      <section className="flex flex-col gap-2 rounded-card bg-card p-5 shadow-card" aria-labelledby="certification-guide-title">
        <h2 id="certification-guide-title" className="text-base font-bold">배지와 인증 안내</h2>
        <p className="text-caption text-muted-foreground">사용자가 누른 인증 기록을 기준으로 해요.</p>
        <p className="text-caption text-muted-foreground">운동량·건강 상태를 검증하는 배지는 아니에요.</p>
      </section>

      {!participation && enrollmentEnded ? <p className="text-center text-sm font-bold text-muted-foreground">모집이 끝났어요</p> : null}
      {!participation && enrollmentNotStarted ? <p className="text-center text-sm font-bold text-muted-foreground">아직 모집 전이에요</p> : null}
      <Button
        disabled={cannotJoin}
        onClick={() => participation ? navigate(`${base}/participations/${participation.id}`) : join()}
      >
        {participation ? '진행 보기' : '참여하기'}
      </Button>
    </main>
  );
}
