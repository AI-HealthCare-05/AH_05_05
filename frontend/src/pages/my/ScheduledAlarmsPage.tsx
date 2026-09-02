import { useEffect, useState } from 'react';
import { BellRing } from 'lucide-react';
import { useNavigate } from 'react-router';
import {
  getActiveScheduledAlarms,
  type ScheduledAlarm,
} from '@/entities/alarm';
import { Card, Header } from '@/shared/ui';

interface ScheduledAlarmsPageProps {
  alarmLoader?: () => Promise<ScheduledAlarm[]>;
}

const ALARM_TYPE_LABELS: Record<string, string> = {
  MEDICATION: '복약',
  NUTRIENT: '영양제',
  FOLLOW_UP_VISIT: '진료일정',
  GUIDE_CHECK: '회복 안내',
};

const MEAL_SLOT_LABELS: Record<string, string> = {
  MORNING: '아침',
  LUNCH: '점심',
  EVENING: '저녁',
  BEDTIME: '자기전',
};

export function ScheduledAlarmsPage({
  alarmLoader = getActiveScheduledAlarms,
}: ScheduledAlarmsPageProps) {
  const navigate = useNavigate();
  const [alarms, setAlarms] = useState<ScheduledAlarm[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    alarmLoader()
      .then((items) => {
        if (!cancelled) setAlarms(items);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '예약된 알림을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [alarmLoader]);

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="예약된 알림" onBack={() => navigate(-1)} />
      <main className="flex flex-1 flex-col gap-3 overflow-y-auto px-page-x py-5">
        {loadError ? (
          <Card title="예약된 알림을 불러오지 못했어요">{loadError}</Card>
        ) : alarms === null ? (
          <p className="text-sm text-muted-foreground">예약된 알림을 불러오는 중...</p>
        ) : alarms.length === 0 ? (
          <Card title="예약된 알림이 없어요.">알림 시간을 정하면 이곳에서 확인할 수 있어요.</Card>
        ) : (
          <section aria-label="예약된 알림 목록" className="flex flex-col gap-3">
            {alarms.map((alarm) => (
              <article
                key={alarm.id}
                className="flex min-h-24 items-start gap-3 rounded-card bg-card p-4 shadow-card"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-pill bg-primary-bg text-primary-strong">
                  <BellRing aria-hidden className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="text-base font-bold text-foreground">{alarm.title}</h2>
                  {alarm.message && (
                    <p className="mt-1 text-sm text-muted-foreground">{alarm.message}</p>
                  )}
                  <p className="mt-2 text-sm font-bold text-primary-strong tnum">
                    {formatScheduledAt(alarm.scheduledAt)}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {alarmLabel(alarm)}
                  </p>
                </div>
              </article>
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

function alarmLabel(alarm: ScheduledAlarm): string {
  const typeLabel = ALARM_TYPE_LABELS[alarm.alarmType] ?? '알림';
  const slotLabel = alarm.mealSlot ? MEAL_SLOT_LABELS[alarm.mealSlot] : null;
  return slotLabel ? `${typeLabel} · ${slotLabel}` : typeLabel;
}

function formatScheduledAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
