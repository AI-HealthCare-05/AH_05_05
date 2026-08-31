import { useEffect, useState } from 'react';
import { ChevronRight, Plus } from 'lucide-react';
import { useNavigate } from 'react-router';
import {
  getMedicationOverviews,
  type MedicationOverview,
} from '@/entities/medication';
import { BottomTabbar, Button, Card, Header, type TabKey } from '@/shared/ui';

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

interface MedicationsPageProps {
  overviewsLoader?: () => Promise<MedicationOverview[]>;
}

export function MedicationsPage({
  overviewsLoader = getMedicationOverviews,
}: MedicationsPageProps) {
  const navigate = useNavigate();
  const [overviews, setOverviews] = useState<MedicationOverview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    overviewsLoader()
      .then((data) => {
        if (!cancelled) setOverviews(data.filter((overview) => overview.medications.length > 0));
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '복용약을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [overviewsLoader]);

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title="복용약"
        onBack={() => navigate(-1)}
        right={
          <button
            type="button"
            aria-label="새 약봉투 등록"
            className="flex size-touch items-center justify-center text-primary"
            onClick={() => navigate('/document-upload')}
          >
            <Plus aria-hidden className="size-6" />
          </button>
        }
      />

      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        {loadError ? (
          <Card title="복용약을 불러오지 못했어요">{loadError}</Card>
        ) : !overviews ? (
          <div
            role="status"
            aria-label="복용약 불러오는 중"
            className="min-h-44 animate-pulse rounded-card bg-muted-bg"
          />
        ) : overviews.length === 0 ? (
          <Card title="복용약을 등록해 주세요." className="gap-4 p-5">
            <Button onClick={() => navigate('/document-upload')}>약봉투 등록하기</Button>
          </Card>
        ) : (
          <section className="flex flex-col gap-3" aria-labelledby="episode-list-title">
            <div className="flex items-baseline justify-between gap-3">
              <h2 id="episode-list-title" className="text-xl font-bold text-foreground">
                처방 기록
              </h2>
              <span className="text-sm text-muted-foreground tnum">{overviews.length}개</span>
            </div>
            {overviews.map((overview) => (
              <EpisodeCard
                key={overview.recordId}
                overview={overview}
                onClick={() => navigate(`/medications/${overview.recordId}`)}
              />
            ))}
          </section>
        )}
      </main>

      <BottomTabbar
        active="medication"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
    </div>
  );
}

function EpisodeCard({
  overview,
  onClick,
}: {
  overview: MedicationOverview;
  onClick: () => void;
}) {
  const active = overview.daysRemaining > 0;
  return (
    <button
      type="button"
      aria-label={`${formatDate(overview.start.date)} 처방 · 약 ${overview.medications.length}개 · ${
        active ? '복용 중' : '복용 완료'
      }`}
      onClick={onClick}
      className="flex min-h-24 w-full items-center gap-3 rounded-card bg-card p-4 text-left shadow-card"
    >
      <span className="min-w-0 flex-1">
        <strong className="block text-lg text-foreground">
          {formatDate(overview.start.date)} 처방
        </strong>
        <span className="mt-1 block text-sm text-muted-foreground tnum">
          {formatPeriod(overview.start.date, overview.endDate)} · 약 {overview.medications.length}개
        </span>
      </span>
      <span
        className={`shrink-0 rounded-pill px-3 py-1.5 text-sm font-bold ${
          active
            ? 'bg-primary-bg text-primary-strong'
            : 'bg-muted-bg text-muted-foreground'
        }`}
      >
        {active ? '복용 중' : '복용 완료'}
      </span>
      <ChevronRight aria-hidden className="size-5 shrink-0 text-disabled-foreground" />
    </button>
  );
}

function formatDate(value: string): string {
  const [, month, day] = value.split('-');
  return month && day ? `${Number(month)}월 ${Number(day)}일` : value;
}

function formatPeriod(from: string, to: string): string {
  const [, fromMonth, fromDay] = from.split('-').map(Number);
  const [, toMonth, toDay] = to.split('-').map(Number);
  return fromMonth === toMonth
    ? `${fromMonth}월 ${fromDay}일 ~ ${toDay}일`
    : `${fromMonth}월 ${fromDay}일 ~ ${toMonth}월 ${toDay}일`;
}
