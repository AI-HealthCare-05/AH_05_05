import { ArrowRight, Check } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';

import { useChallengeMock } from '@/features/challenges';

function challengeBase(pathname: string) {
  return pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
}

function frequencyLabel(type: 'daily' | 'weekly', dailyDays?: number, weekly?: { days: number; weeks: number }) {
  return type === 'daily'
    ? `참여일부터 ${dailyDays}일 · 매일 인증`
    : `참여일부터 ${weekly!.weeks * 7}일 · 주 ${weekly!.days}회 인증`;
}

export function ChallengeBrowsePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const base = challengeBase(location.pathname);
  const { definitions, participations, demoToday } = useChallengeMock();
  const official = definitions.filter(
    (definition) =>
      definition.kind === 'official' &&
      definition.enrollmentStart &&
      definition.enrollmentEnd &&
      definition.enrollmentEnd >= demoToday,
  );

  return (
    <main className="flex flex-col gap-4 px-page-x py-5">
      <h1 className="text-[22px] font-bold leading-6 text-foreground">챌린지</h1>
      <nav aria-label="챌린지 보기" className="grid h-11 grid-cols-2 rounded-input bg-muted-bg p-1">
        <Link to={base} className="flex items-center justify-center rounded-[9px] text-sm font-medium text-muted-foreground">마이</Link>
        <Link aria-current="page" to={`${base}/browse`} className="flex items-center justify-center rounded-[9px] bg-card text-sm font-bold text-primary shadow-card">둘러보기</Link>
      </nav>

      <Link to={`${base}/tailored`} className="flex min-h-12 items-center justify-between rounded-button border border-primary bg-card px-4 text-sm font-bold text-primary">
        <span>내 기록으로 맞춤 챌린지 보기</span>
        <ArrowRight aria-hidden className="size-5" />
      </Link>

      <Link to={`${base}/participations/part-official-active`} className="flex flex-col gap-2 rounded-card bg-primary-bg p-5 text-foreground">
        <Check aria-hidden className="size-11 text-primary" />
        <strong className="text-base">걷기로 채우는 나의 일주일</strong>
        <span className="text-caption text-primary">참여한 날부터 7일 · 하루 한 번 인증</span>
      </Link>

      <section aria-labelledby="official-challenges-title" className="flex flex-col gap-3">
        <h2 id="official-challenges-title" className="text-lg font-bold">공식 챌린지</h2>
        {official.map((definition) => {
          const frequency = definition.frequency;
          const participation = participations.find((item) => item.challengeId === definition.id);
          return (
            <button
              key={definition.id}
              type="button"
              aria-label={`${definition.title} 자세히 보기`}
              onClick={() => navigate(participation ? `${base}/participations/${participation.id}` : `${base}/official/${definition.id}`)}
              className="flex w-full flex-col gap-2 rounded-card bg-card p-5 text-left shadow-card"
            >
              <span className="text-base font-bold text-foreground">{definition.title}</span>
              <span className="text-sm text-primary">{definition.description}</span>
              <span className="text-caption text-muted-foreground">
                {frequency.type === 'daily'
                  ? frequencyLabel('daily', frequency.durationDays)
                  : frequencyLabel('weekly', undefined, { days: frequency.targetDaysPerWeek, weeks: frequency.durationWeeks })}
              </span>
              <span className="text-caption text-muted-foreground">공식 · 모집 {definition.enrollmentStart!.slice(5).replace('-', '.')} ~ {definition.enrollmentEnd!.slice(5).replace('-', '.')}</span>
              <span className="text-caption font-bold text-primary">{participation ? '참여 중 ›' : '자세히 보기 ›'}</span>
            </button>
          );
        })}
      </section>

      <Link to={`${base}/create`} className="flex flex-col gap-1 py-2">
        <span className="text-caption text-muted-foreground">나만의 작은 목표로 시작할까요?</span>
        <span className="text-sm font-bold text-primary">나만의 챌린지 만들기 ›</span>
      </Link>
    </main>
  );
}
