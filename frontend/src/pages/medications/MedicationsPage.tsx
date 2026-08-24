import { useEffect, useState } from 'react';
import { ChevronRight, Plus } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import {
  getMedicationOverview,
  saveMedicationSchedule,
  type MealSlot,
  type MedicationOverview,
  type MedicationOverviewItem,
} from '@/entities/medication';
import { BottomTabbar, Card, ErrorDialog, Header, ImageViewer, type TabKey } from '@/shared/ui';
import { MedicationSlotSheet } from './MedicationSlotSheet';

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
  const [editingMedication, setEditingMedication] = useState<MedicationOverviewItem | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [imageViewerOpen, setImageViewerOpen] = useState(false);

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

  async function saveMedicationSlots(slots: MealSlot[]) {
    if (!overview || !editingMedication) return;
    setSaveError(null);
    const nextMedications = overview.medications.map((medication) =>
      medication.medicationId === editingMedication.medicationId
        ? { ...medication, slots }
        : medication,
    );
    try {
      await saveMedicationSchedule({
        recordId: overview.recordId,
        start: overview.start,
        mealTimes: overview.mealTimes,
        medications: nextMedications
          .filter((medication) => !medication.asNeeded)
          .map((medication) => ({
            medicationId: medication.medicationId,
            slots: medication.slots,
          })),
      });
      setOverview({ ...overview, medications: nextMedications });
      setEditingMedication(null);
      toast.success('복용 시간을 바꿨어요.');
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '복용 시간을 저장하지 못했어요.');
    }
  }

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
                    {formatDate(overview.start.date)}부터 복용 중
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
              aria-label="등록한 약봉투 원본 크게 보기"
              className="overflow-hidden rounded-card bg-card text-left shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setImageViewerOpen(true)}
            >
              <img
                src={overview.documentImageUrl}
                alt="등록한 약봉투 원본"
                className="h-24 w-full object-cover object-top"
              />
              <span className="flex min-h-touch items-center justify-between gap-3 px-4 text-sm font-bold text-foreground">
                이 기록의 약봉투 원본
                <span className="text-muted-foreground">크게 보기</span>
              </span>
            </button>

            <button
              type="button"
              className="flex min-h-20 items-center gap-3 rounded-card bg-card px-4 py-3 text-left shadow-card"
              onClick={() =>
                navigate('/medication-alarm-times')
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
                <MedicationCard
                  key={medication.medicationId}
                  medication={medication}
                  onClick={
                    medication.asNeeded ? undefined : () => setEditingMedication(medication)
                  }
                />
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
      <MedicationSlotSheet
        open={editingMedication !== null}
        medication={editingMedication}
        onOpenChange={(open) => {
          if (!open) setEditingMedication(null);
        }}
        onSave={saveMedicationSlots}
      />
      <ErrorDialog
        open={saveError !== null}
        title="복용 시간을 저장하지 못했어요"
        message={saveError ?? ''}
        retryLabel="확인"
        onRetry={() => setSaveError(null)}
      />
      {overview && (
        <ImageViewer
          open={imageViewerOpen}
          src={overview.documentImageUrl}
          title="약봉투 원본 크게 보기"
          onOpenChange={setImageViewerOpen}
        />
      )}
    </div>
  );
}

function MedicationCard({
  medication,
  onClick,
}: {
  medication: MedicationOverviewItem;
  onClick?: () => void;
}) {
  return (
    <Card className="gap-3 p-4" onClick={onClick}>
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
