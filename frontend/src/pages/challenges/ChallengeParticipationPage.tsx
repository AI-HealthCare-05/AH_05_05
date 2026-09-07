import { ArrowLeft, Check } from 'lucide-react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';

import { useChallengeMock } from '@/features/challenges';
import { Button } from '@/shared/ui/Button';
import { ChallengeChecklistView } from './ChallengeChecklistView';
import { ChallengeBadgeArt } from './ChallengeBadgeArt';

function challengeBase(pathname: string) {
  return pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
}

function dateLabel(date: string) {
  const [year, month, day] = date.split('-');
  return `${year}.${Number(month)}.${Number(day)}`;
}

function datesBetween(start: string, end: string): string[] {
  const dates: string[] = [];
  const current = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  while (current <= last) {
    dates.push(current.toISOString().slice(0, 10));
    current.setUTCDate(current.getUTCDate() + 1);
  }
  return dates;
}

export function ChallengeParticipationPage() {
  const { participationId = '' } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const base = challengeBase(location.pathname);
  const { participations, definitions, badges, demoToday, checkIn } = useChallengeMock();
  const participation = participations.find((item) => item.id === participationId);
  const definition = definitions.find((item) => item.id === participation?.challengeId);

  if (!participation || !definition) {
    return (
      <section className="flex flex-col gap-4">
        <h1 className="text-xl font-bold">참여 기록을 찾을 수 없어요</h1>
        <Button variant="secondary" onClick={() => navigate(base)}>챌린지로 돌아가기</Button>
      </section>
    );
  }

  if (participation.kind === 'review' || participation.kind === 'visit') {
    return (
      <main className="flex flex-col gap-4 px-page-x py-5">
        <header className="flex items-center gap-3">
          <button type="button" aria-label="뒤로 가기" onClick={() => navigate(base)} className="flex size-11 items-center justify-center rounded-pill"><ArrowLeft aria-hidden className="size-5" /></button>
          <h1 className="text-[22px] font-bold">{participation.title}</h1>
        </header>
        <ChallengeChecklistView participation={participation} />
      </main>
    );
  }

  const badge = badges.find((item) => item.id === participation.badgeId);
  const future = participation.startDate > demoToday;
  const frequencyUnit =
    participation.kind === 'medication' || participation.kind === 'supplement'
      ? '회'
      : definition.frequency.type === 'daily'
        ? '일'
        : '회';
  const visibleDates = datesBetween(participation.startDate, participation.endDate);

  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <header className="flex items-center gap-3">
        <button type="button" aria-label="뒤로 가기" onClick={() => navigate(base)} className="flex size-11 shrink-0 items-center justify-center rounded-pill"><ArrowLeft aria-hidden className="size-5" /></button>
        <div className="min-w-0">
          <h1 className="truncate text-[22px] font-bold leading-7">{participation.title}</h1>
          <p className="text-caption text-muted-foreground">내 수행 기간 · {dateLabel(participation.startDate)} ~ {dateLabel(participation.endDate)}</p>
        </div>
      </header>

      {participation.todayCompleted ? (
        <section className="flex gap-3 rounded-card bg-primary-bg p-5" aria-label="오늘 인증 결과">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-pill bg-primary text-card"><Check aria-hidden className="size-5" /></span>
          <div>
            <h2 className="text-base font-bold">오늘의 실천을 기록했어요</h2>
            <p className="mt-1 text-caption text-primary">같은 날 중복으로 인증되지 않아요.</p>
          </div>
        </section>
      ) : null}

      {participation.status === 'active' && (participation.kind === 'official' || participation.kind === 'personal') ? (
        <section className="flex flex-col gap-2 rounded-card bg-primary-bg p-5" aria-label="오늘의 챌린지 진행">
          <h2 className="text-base font-bold">오늘도 한 걸음</h2>
          <p className="text-sm text-primary">{participation.completed} / {participation.target}{frequencyUnit} 인증 · {participation.todayCompleted ? '오늘 인증 완료' : '오늘은 아직 미인증'}</p>
          <div className="h-2 overflow-hidden rounded-pill bg-border"><div className="h-full rounded-pill bg-primary" style={{ width: `${participation.percent}%` }} /></div>
        </section>
      ) : null}

      {participation.status === 'achieved' ? (
        <section className="flex flex-col items-center gap-2 rounded-card bg-primary-bg p-5 text-center" aria-label="챌린지 완료 결과">
          {badge ? <ChallengeBadgeArt badge={badge} className="size-16" /> : null}
          <h2 className="text-lg font-bold">챌린지를 완주했어요</h2>
          {badge ? <Link to={`${base}/badges/${badge.id}`} className="text-sm font-bold text-primary">{badge.name} 자세히 보기 ›</Link> : null}
        </section>
      ) : participation.status === 'missed' ? (
        <section className="rounded-card bg-muted-bg p-5 text-center">
          <h2 className="text-base font-bold">이번 도전은 여기까지예요</h2>
          <p className="mt-1 text-caption text-muted-foreground">남긴 기록은 지난 기록에서 언제든 볼 수 있어요.</p>
        </section>
      ) : null}

      <section className="flex flex-col gap-3 rounded-card bg-card p-5 shadow-card" aria-labelledby="my-record-title">
        <div className="flex items-center justify-between gap-3">
          <h2 id="my-record-title" className="text-base font-bold">내 인증 기록</h2>
          <span className="text-sm font-bold text-primary">{participation.completed} / {participation.target}{frequencyUnit} 인증</span>
        </div>
        <div className="grid grid-cols-7 gap-1" aria-label="날짜별 인증 기록">
          {visibleDates.map((date) => {
            const checked = participation.checkInDates.includes(date);
            return (
              <div key={date} className="flex min-w-0 flex-col items-center gap-1">
                <span className="text-micro text-muted-foreground">{Number(date.slice(-2))}</span>
                <span aria-label={`${date} ${checked ? '인증 완료' : '미인증'}`} className={`flex aspect-square w-full max-w-9 items-center justify-center rounded-[5px] ${checked ? 'bg-primary text-card' : 'bg-muted-bg text-tertiary-foreground'}`}>
                  {checked ? <Check aria-hidden className="size-4" /> : '·'}
                </span>
              </div>
            );
          })}
        </div>
        <div className="h-2 overflow-hidden rounded-pill bg-border">
          <div className="h-full rounded-pill bg-primary" style={{ width: `${participation.percent}%` }} />
        </div>
      </section>

      <section className="rounded-card bg-card p-5 shadow-card" aria-labelledby="today-goal-title">
        <h2 id="today-goal-title" className="text-base font-bold">오늘의 목표</h2>
        <p className="mt-1 text-sm text-muted-foreground">{definition.taskLabel}</p>
        {participation.targetSummary ? <p className="mt-2 rounded-input bg-muted-bg p-3 text-caption text-foreground">선택한 대상 · {participation.targetSummary}</p> : null}
      </section>

      <section className="rounded-card bg-card p-5 text-caption text-muted-foreground shadow-card" aria-labelledby="certification-note-title">
        <h2 id="certification-note-title" className="mb-2 text-base font-bold text-foreground">배지와 인증 안내</h2>
        <p>{participation.kind === 'medication' || participation.kind === 'supplement' ? '홈에서 남긴 복용 기록이 자동으로 반영돼요.' : '인증 내용은 내가 누른 기록을 기준으로 해요.'}</p>
      </section>

      {participation.status === 'active' && (participation.kind === 'official' || participation.kind === 'personal') ? (
        <Button disabled={participation.todayCompleted || future} onClick={() => checkIn(participation.id)}>
          {future ? '시작 전이에요' : participation.todayCompleted ? '오늘 인증 완료' : '했어요'}
        </Button>
      ) : null}
    </main>
  );
}
