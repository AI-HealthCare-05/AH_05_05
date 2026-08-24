import { useEffect, useState } from 'react';
import { ChevronRight, Plus } from 'lucide-react';
import { useNavigate } from 'react-router';
import {
  getMedicationOverview,
  type MealSlot,
  type MedicationOverview,
  type MedicationOverviewItem,
} from '@/entities/medication';
import { BottomTabbar, Card, Header, type TabKey } from '@/shared/ui';

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

const SLOT_LABEL: Record<MealSlot, string> = {
  morning: '아침',
  lunch: '점심',
  evening: '저녁',
  bedtime: '취침 전',
};

export function MedicationsPage() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<MedicationOverview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMedicationOverview()
      .then((data) => {
        if (!cancelled) setOverview(data);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '복용약을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
        ) : !overview ? (
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        ) : (
          <>
            <Card tone="info" className="gap-2 p-4">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="text-sm text-muted-foreground">
                    {formatDate(overview.startDate)}부터 복용 중
                  </p>
                  <p className="mt-1 text-2xl font-bold text-foreground">
                    {overview.daysRemaining}일 남음
                  </p>
                </div>
                <span className="text-sm font-bold text-success-strong">복용 중</span>
              </div>
            </Card>

            <button
              type="button"
              className="flex min-h-20 items-center gap-3 rounded-card bg-card px-4 py-3 text-left shadow-card"
              onClick={() =>
                navigate('/medication-schedule', {
                  state: { recordId: overview.recordId, dispensedDate: overview.startDate },
                })
              }
            >
              <span className="min-w-0 flex-1">
                <strong className="block text-lg text-foreground">알림 시간</strong>
                <span className="mt-1 block text-sm text-muted-foreground tnum">
                  아침 {overview.mealTimes.morning} · 점심 {overview.mealTimes.lunch} · 저녁{' '}
                  {overview.mealTimes.evening}
                </span>
              </span>
              <ChevronRight aria-hidden className="size-5 text-disabled-foreground" />
            </button>

            <section className="flex flex-col gap-3" aria-labelledby="medication-list-title">
              <h2 id="medication-list-title" className="text-xl font-bold text-foreground">
                약 {overview.medications.length}개
              </h2>
              {overview.medications.map((medication) => (
                <MedicationCard key={medication.medicationId} medication={medication} />
              ))}
            </section>
          </>
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

function MedicationCard({ medication }: { medication: MedicationOverviewItem }) {
  return (
    <Card className="gap-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-lg font-bold text-foreground">
          {medication.name} {medication.dose}
        </p>
        {medication.daysRemaining !== null && (
          <span
            className={
              medication.untilComplete
                ? 'shrink-0 text-sm font-bold text-warning-strong'
                : 'shrink-0 text-sm text-muted-foreground'
            }
          >
            {medication.daysRemaining}일 남음
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {medication.asNeeded ? (
          <span className="rounded-pill bg-muted-bg px-3 py-1.5 text-sm text-muted-foreground">
            필요할 때만 · 알림 없음
          </span>
        ) : (
          <>
            {medication.slots.map((slot) => (
              <span
                key={slot}
                className="rounded-pill bg-muted-bg px-3 py-1.5 text-sm text-muted-foreground"
              >
                {SLOT_LABEL[slot]}
              </span>
            ))}
            {medication.untilComplete && (
              <span className="rounded-pill bg-warning-bg px-3 py-1.5 text-sm text-warning-strong">
                끝까지 복용
              </span>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

function formatDate(value: string): string {
  const [, month, day] = value.split('-');
  return month && day ? `${Number(month)}월 ${Number(day)}일` : value;
}
