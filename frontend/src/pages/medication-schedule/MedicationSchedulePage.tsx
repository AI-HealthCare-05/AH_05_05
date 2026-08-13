import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button, Card, Header } from '@/shared/ui';
import { cn } from '@/shared/lib/cn';
import {
  getMedicationSchedule,
  saveMedicationSchedule,
  type MedicationSchedule,
  type StartPeriod,
} from '@/entities/medication';
import { TimePickerSheet } from './TimePickerSheet';
import { defaultTimesFor, formatSlotLabel } from './timePresets';

/**
 * REQ-CARE-003 · Figma `09 복약 시간 설정` (125:50) / `09-A 시간 선택` (114:11)
 *
 * 확인한 어긋남과 처리:
 * - REQ는 시간 지정 방법으로 프리셋과 시·분 선택 박스를 둘 다 요구하는데 Figma 시트에는
 *   프리셋이 없어, 기획 확인 후 시트에 프리셋 칩을 추가했습니다(TimePickerSheet 주석 참고).
 * - `09-A`에만 "복용 시작 시점" 필드가 빠져 있는데(09·09-B에는 있음) 나중에 추가된 필드가
 *   09-A에 반영되지 않은 것으로 보고 09 기준으로 맞췄습니다.
 *
 * 범위 메모: `09-B 기존 저장 시각 프리필`(116:241)은 GET 응답의 startPeriod·times가
 * 채워져 오면 그대로 프리필되는 같은 화면입니다(스펙 5-3). 별도 컴포넌트를 만들지 않고
 * 이 화면이 두 경우를 모두 처리합니다. 재설정 진입점(마이페이지)은 아직 없습니다.
 */
interface ScheduleLocationState {
  recordId?: number;
}

const START_PERIODS: Array<{ value: StartPeriod; label: string }> = [
  { value: 'morning', label: '아침' },
  { value: 'lunch', label: '점심' },
  { value: 'evening', label: '저녁' },
];

interface EditingSlot {
  medicationId: number;
  index: number;
}

export function MedicationSchedulePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as ScheduleLocationState | null) ?? {};
  const recordId = state.recordId ?? 12;

  const [schedule, setSchedule] = useState<MedicationSchedule | null>(null);
  const [startPeriod, setStartPeriod] = useState<StartPeriod | null>(null);
  /** medicationId → 슬롯 시각 배열 */
  const [times, setTimes] = useState<Record<number, string[]>>({});
  const [editingSlot, setEditingSlot] = useState<EditingSlot | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getMedicationSchedule(recordId).then((data) => {
      if (cancelled) return;
      setSchedule(data);
      setStartPeriod(data.startPeriod);

      // 저장값이 있으면 그대로 프리필(09-B), 없으면 복용 횟수만큼 기본 시각 생성.
      const next: Record<number, string[]> = {};
      for (const med of data.medications) {
        if (med.timesPerDay === null) continue;
        next[med.medicationId] =
          med.times.length > 0 ? med.times : defaultTimesFor(med.timesPerDay);
      }
      setTimes(next);
    });
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  function applyTime(time: string) {
    if (!editingSlot) return;
    setTimes((prev) => {
      const slots = [...(prev[editingSlot.medicationId] ?? [])];
      slots[editingSlot.index] = time;
      return { ...prev, [editingSlot.medicationId]: slots };
    });
    setEditingSlot(null);
  }

  async function persist(
    period: StartPeriod,
    payloadTimes: Record<number, string[]>,
    reason: 'schedule-saved' | 'schedule-skipped',
  ) {
    if (!schedule) return;
    setSaving(true);
    try {
      await saveMedicationSchedule({
        recordId,
        startPeriod: period,
        medications: schedule.medications
          .filter((m) => m.timesPerDay !== null)
          .map((m) => ({ medicationId: m.medicationId, times: payloadTimes[m.medicationId] ?? [] })),
      });
      toast.success('복약 시간을 저장했어요');
      navigate('/dev/flow-complete', { state: { reason } });
    } finally {
      setSaving(false);
    }
  }

  function handleSave() {
    if (!startPeriod) return;
    void persist(startPeriod, times, 'schedule-saved');
  }

  /**
   * "기본 시간으로 건너뛰기" — 스펙 5-3: 건너뛰면 프론트가 기본 프리셋 시각을 보냅니다.
   * 복용 시작 시점은 아직 고르지 않았을 수 있어 기본값으로 아침을 보냅니다.
   */
  function handleSkip() {
    if (!schedule) return;
    const defaults: Record<number, string[]> = {};
    for (const med of schedule.medications) {
      if (med.timesPerDay === null) continue;
      defaults[med.medicationId] = defaultTimesFor(med.timesPerDay);
    }
    void persist(startPeriod ?? 'morning', defaults, 'schedule-skipped');
  }

  if (!schedule) {
    return (
      <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
        <Header title="복약 시간 설정" onBack={() => navigate(-1)} />
        <main className="flex flex-1 items-center justify-center">
          <p className="text-sm text-muted-foreground">불러오는 중...</p>
        </main>
      </div>
    );
  }

  const editingMed = editingSlot
    ? schedule.medications.find((m) => m.medicationId === editingSlot.medicationId)
    : undefined;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="복약 시간 설정" onBack={() => navigate(-1)} />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        <p className="text-base text-foreground">약마다 실제 복용 시간을 확인해주세요.</p>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <p className="text-sm font-bold text-foreground">복용 시작 시점</p>
            <p className="text-sm text-muted-foreground">
              처음 복용을 시작하는 시간대를 선택해주세요.
            </p>
          </div>
          <div className="flex gap-2">
            {START_PERIODS.map((period) => {
              const selected = period.value === startPeriod;
              return (
                <button
                  key={period.value}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setStartPeriod(period.value)}
                  className={cn(
                    'h-touch flex-1 rounded-input border text-sm transition-colors',
                    selected
                      ? 'border-primary bg-primary font-bold text-card'
                      : 'border-border bg-primary-bg text-foreground hover:bg-muted-bg',
                  )}
                >
                  {period.label}
                </button>
              );
            })}
          </div>
        </div>

        {schedule.medications.map((med) =>
          med.timesPerDay === null ? (
            // 필요 시 복용 — 시각을 지정하지 않습니다(스펙 5-3).
            <Card key={med.medicationId} title={`${med.name} ${med.dose}`}>
              필요할 때만 복용 · {med.timing}
            </Card>
          ) : (
            <div key={med.medicationId} className="flex flex-col gap-2">
              <Card title={`${med.name} ${med.dose}`}>
                1일 {med.timesPerDay}회 · {med.timing}
              </Card>
              <div className="flex gap-2">
                {(times[med.medicationId] ?? []).map((time, index) => (
                  <button
                    // 같은 시각이 두 슬롯에 들어갈 수 있어 index를 key로 씁니다.
                    key={index}
                    type="button"
                    onClick={() => setEditingSlot({ medicationId: med.medicationId, index })}
                    className="h-touch flex-1 rounded-input border border-input bg-card px-3 text-base text-foreground transition-colors hover:bg-muted-bg"
                  >
                    {formatSlotLabel(time)}
                  </button>
                ))}
              </div>
            </div>
          ),
        )}

        <p className="text-sm text-muted-foreground">
          저장한 시간에 알림을 보내요. 나중에 마이페이지에서 변경할 수 있어요.
        </p>

        <div className="flex-1" />

        <div className="flex flex-col gap-2 pb-4">
          <Button onClick={handleSave} disabled={saving || !startPeriod}>
            {saving ? '저장 중...' : '저장하고 계속'}
          </Button>
          <Button variant="secondary" onClick={handleSkip} disabled={saving}>
            기본 시간으로 건너뛰기
          </Button>
        </div>
      </main>

      <TimePickerSheet
        open={editingSlot !== null}
        description={
          editingMed
            ? `${editingMed.name} ${editingMed.dose} · ${(editingSlot?.index ?? 0) + 1}번째 복용 시각`
            : ''
        }
        value={
          editingSlot ? (times[editingSlot.medicationId]?.[editingSlot.index] ?? '08:00') : '08:00'
        }
        onApply={applyTime}
        onCancel={() => setEditingSlot(null)}
      />
    </div>
  );
}
