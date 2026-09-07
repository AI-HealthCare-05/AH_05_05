import { useLocation } from 'react-router';
import { Link } from 'react-router';
import { useChallengeMock } from '@/features/challenges';

function compactDate(value: string) {
  const [, month, day] = value.split('-');
  return `${Number(month)}.${Number(day)}`;
}

export function HomeChallengeSummary({ empty = false }: { empty?: boolean }) {
  const { participations, medicationEpisodes } = useChallengeMock();
  const location = useLocation();
  const base = location.pathname.startsWith('/dev/') ? '/dev/challenges' : '/challenges';
  const allActive = empty ? [] : participations.filter((item) => item.status === 'active');
  const medication = empty ? [] : participations.filter((item) =>
    item.kind === 'medication' && medicationEpisodes.some((episode) => episode.id === item.episodeId),
  );
  const others = allActive.filter((item) => item.kind !== 'medication');
  const supplement = others.filter((item) => item.kind === 'supplement');
  const active = [...medication, ...(supplement.length ? supplement : others).slice(0, medication.length ? 1 : 2)];

  return (
    <section aria-labelledby="home-challenge-title" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 id="home-challenge-title" className="text-lg font-bold text-foreground">
            챌린지
          </h2>
          <span className="rounded-pill bg-muted-bg px-2 py-1 text-micro text-muted-foreground">
            예시 데이터
          </span>
        </div>
        <Link to={base} className="min-h-touch py-3 text-caption font-bold text-primary">
          전체 보기
        </Link>
      </div>
      <div className="flex min-h-[132px] flex-col justify-center gap-3 rounded-card bg-card px-4 py-3 shadow-card">
        {medication.length ? (
          <div className="space-y-1 border-b border-border pb-3">
            <h3 className="text-sm font-bold">복약 챌린지 · 처방별 진행</h3>
            <p className="text-xs text-muted-foreground">진행 중 {medication.filter((item) => item.status === 'active').length}개 · 달성 {medication.filter((item) => item.status === 'achieved').length}개</p>
          </div>
        ) : null}
        {active.length === 0 ? (
          <>
            <p className="text-sm font-bold text-foreground">참여 중인 챌린지가 없어요</p>
            <Link
              to={`${base}/tailored`}
              className="flex min-h-touch items-center justify-center rounded-input bg-primary-bg text-sm font-bold text-primary"
            >
              맞춤 챌린지 보기 ›
            </Link>
          </>
        ) : (
          active.map((participation) => {
            const title =
              participation.kind === 'supplement'
                ? `${participation.title} 챌린지`
                : participation.title;
            return <Link
              key={participation.id}
              to={`${base}/participations/${participation.id}`}
              aria-label={`${title}, ${participation.percent}% 달성, 상세 보기`}
              className="group flex min-h-12 flex-col gap-1"
            >
              <span className="flex items-center justify-between gap-2 text-xs font-bold text-foreground">
                <span className="truncate">{title}</span>
                <span aria-hidden className="text-base text-tertiary-foreground">›</span>
              </span>
              <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="tnum">
                  {compactDate(participation.startDate)} ~ {compactDate(participation.endDate)}
                </span>
                <span>{participation.percent}% {participation.status === 'achieved' ? '달성 · 배지 획득' : '달성했어요'}</span>
              </span>
              <span className="h-2 overflow-hidden rounded-pill bg-border" aria-hidden>
                <span
                  className="block h-full rounded-pill bg-primary"
                  style={{ width: `${Math.max(0, Math.min(100, participation.percent))}%` }}
                />
              </span>
            </Link>;
          })
        )}
      </div>
    </section>
  );
}
