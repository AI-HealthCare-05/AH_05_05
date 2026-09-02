import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import type { MealSlot, MealTimes } from '@/entities/medication';
import {
  getNotifySettings,
  updateNotifySettings,
  type MedicationTimes,
  type NotifySettings,
} from '@/entities/settings';
import { cn } from '@/shared/lib/cn';
import { MEAL_SLOTS, isMealTimeOrderValid } from '@/shared/model/mealSlot';
import { Card, ErrorDialog, Header, TimePickerSheet } from '@/shared/ui';

const SETTINGS_FIELD_BY_SLOT: Record<MealSlot, keyof MedicationTimes> = {
  morning: 'morningMedicationTime',
  lunch: 'lunchMedicationTime',
  evening: 'eveningMedicationTime',
  bedtime: 'bedtimeMedicationTime',
};

function mealTimesFromSettings(settings: NotifySettings): MealTimes {
  return {
    morning: settings.morningMedicationTime,
    lunch: settings.lunchMedicationTime,
    evening: settings.eveningMedicationTime,
    bedtime: settings.bedtimeMedicationTime,
  };
}

export function MedicationAlarmTimesPage() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<NotifySettings | null>(null);
  const [editingSlot, setEditingSlot] = useState<MealSlot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<{ message: string; retry: () => void } | null>(null);
  const [timeOrderError, setTimeOrderError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getNotifySettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '알림 시간을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function persist(slot: MealSlot, time: string) {
    setSaveError(null);
    try {
      const saved = await updateNotifySettings({ [SETTINGS_FIELD_BY_SLOT[slot]]: time });
      setSettings(saved);
      setEditingSlot(null);
      toast.success('알림 시간을 바꿨어요.');
    } catch (error: unknown) {
      setSaveError({
        message: error instanceof Error ? error.message : '알림 시간을 저장하지 못했어요.',
        retry: () => void persist(slot, time),
      });
    }
  }

  function applyTime(time: string) {
    if (!settings || !editingSlot) return;
    const nextMealTimes = { ...mealTimesFromSettings(settings), [editingSlot]: time };
    if (!isMealTimeOrderValid(nextMealTimes)) {
      setTimeOrderError(true);
      return;
    }
    void persist(editingSlot, time);
  }

  const mealTimes = settings ? mealTimesFromSettings(settings) : null;
  const editingLabel = editingSlot
    ? MEAL_SLOTS.find((slot) => slot.value === editingSlot)?.label
    : undefined;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="알림 시간" onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col px-page-x py-5">
        {loadError ? (
          <Card title="알림 시간을 불러오지 못했어요">{loadError}</Card>
        ) : !mealTimes ? (
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        ) : (
          <section aria-label="알림 시간 네 개" className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              시간을 누르면 바로 바꿀 수 있고, 적용하면 즉시 저장됩니다.
            </p>
            <div className="overflow-hidden rounded-card border border-border bg-card shadow-card">
              {MEAL_SLOTS.map((slot, index) => (
                <button
                  key={slot.value}
                  type="button"
                  onClick={() => setEditingSlot(slot.value)}
                  className={cn(
                    'flex min-h-16 w-full items-center gap-3 px-4 text-left',
                    index > 0 && 'border-t border-border',
                  )}
                >
                  <span className="w-16 text-sm font-bold text-foreground">{slot.label}</span>
                  <span className="text-base text-foreground tnum">{mealTimes[slot.value]}</span>
                  <span aria-hidden className="ml-auto text-muted-foreground">
                    ›
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}
      </main>

      <TimePickerSheet
        open={editingSlot !== null}
        description={editingLabel ? `${editingLabel} 알림 시각` : ''}
        value={editingSlot && mealTimes ? mealTimes[editingSlot] : '08:00'}
        onApply={applyTime}
        onCancel={() => setEditingSlot(null)}
      />
      <ErrorDialog
        open={saveError !== null}
        title="알림 시간을 저장하지 못했어요"
        message={saveError?.message ?? ''}
        onRetry={() => {
          const retry = saveError?.retry;
          setSaveError(null);
          retry?.();
        }}
      />
      <ErrorDialog
        open={timeOrderError}
        title="시간을 적용할 수 없어요"
        message="복약 시간은 아침약 → 점심약 → 저녁약 → 취침약 순서로 설정해주세요."
        retryLabel="확인"
        onRetry={() => setTimeOrderError(false)}
      />
    </div>
  );
}
