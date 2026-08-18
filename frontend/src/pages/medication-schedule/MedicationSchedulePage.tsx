import { useEffect, useState, type MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button, Header, Input } from '@/shared/ui';
import { cn } from '@/shared/lib/cn';
import {
  getMedicationSchedule,
  saveMedicationSchedule,
  type MealSlot,
  type MealTimes,
  type MedicationSchedule,
  type MedicationStartPoint,
} from '@/entities/medication';
import { TimePickerSheet } from './TimePickerSheet';
import {
  DEFAULT_MEAL_TIMES,
  MEAL_SLOTS,
  SLOT_ORDER,
  defaultSlotsFor,
  exceedsSlotCapacity,
  isMealTimeOrderValid,
} from './slotAssignment';

/**
 * REQ-CARE-003 · 통합 슬롯 구조 (2026-08-14 기획 결정)
 *
 * 사용자는 아침약·점심약·저녁약·취침약 시각 4개만 정하고, 약은 "어느 시간에 먹는지"만
 * 가집니다. 약이 4개여도 시각 입력은 4개로 끝납니다.
 *
 * **Figma `09`(125:50)는 아직 옛 구조(약별 시각)입니다.** 이 화면은 작업지시 문서와
 * 이후 피드백이 기준이며 Figma 수정은 별도 작업으로 뒤따릅니다. `09-A 시간 선택` 시트는
 * 구조가 바뀌지 않아 그대로 씁니다(description prop만 다르게 넘깁니다).
 */
interface ScheduleLocationState {
  recordId?: number;
}

/**
 * 오늘 날짜(YYYY-MM-DD). "처음 약을 언제부터 드셨나요?"의 기본값으로만 씁니다.
 *
 * 이 프로젝트는 날짜 계산을 서버에서 하기로 정했지만(기기 시간 의존을 피하려고),
 * 이건 계산이 아니라 사용자가 화면에서 보고 고칠 수 있는 입력값의 초기값입니다.
 * 저장되는 값은 어디까지나 사용자가 확인한 날짜입니다.
 */
function todayISO(): string {
  const now = new Date();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${m}-${d}`;
}

/** "2026-08-14" + lunch → "8월 14일 점심약" */
function formatStartPoint(date: string, slot: MealSlot): string {
  const label = MEAL_SLOTS.find((s) => s.value === slot)?.label ?? '';
  const [, month, day] = date.split('-');
  if (!month || !day) return label;
  return `${Number(month)}월 ${Number(day)}일 ${label}`;
}

export function MedicationSchedulePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as ScheduleLocationState | null) ?? {};
  const recordId = state.recordId ?? 12;

  const [schedule, setSchedule] = useState<MedicationSchedule | null>(null);
  const [mealTimes, setMealTimes] = useState<MealTimes>(DEFAULT_MEAL_TIMES);
  /** medicationId → 시간대 */
  const [slots, setSlots] = useState<Record<number, MealSlot[]>>({});
  const [startDate, setStartDate] = useState('');
  const [startSlot, setStartSlot] = useState<MealSlot | null>(null);
  /** 시각 편집 대상 시간대 */
  const [editingSlot, setEditingSlot] = useState<MealSlot | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getMedicationSchedule(recordId).then((data) => {
      if (cancelled) return;
      setSchedule(data);
      setMealTimes(data.mealTimes ?? DEFAULT_MEAL_TIMES);
      // 저장값 우선(09-B 프리필). 날짜는 비어 있으면 오늘로 채워 사용자가 고치게 합니다.
      setStartDate(data.start?.date ?? todayISO());
      setStartSlot(data.start?.slot ?? null);

      const next: Record<number, MealSlot[]> = {};
      for (const med of data.medications) {
        next[med.medicationId] =
          med.slots.length > 0 ? med.slots : defaultSlotsFor(med.timesPerDay, med.timing);
      }
      setSlots(next);
    });
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  /** 토글. SLOT_ORDER 순서를 유지해 담습니다 — 클릭 순서대로 쌓으면 재진입 시 표시가 흔들립니다. */
  function toggleSlot(medicationId: number, slot: MealSlot) {
    setSlots((prev) => {
      const current = prev[medicationId] ?? [];
      const nextSet = new Set(current);
      if (nextSet.has(slot)) {
        nextSet.delete(slot);
      } else {
        nextSet.add(slot);
      }
      return { ...prev, [medicationId]: SLOT_ORDER.filter((s) => nextSet.has(s)) };
    });
  }

  function applyTime(time: string) {
    if (!editingSlot) return;
    setMealTimes((prev) => ({ ...prev, [editingSlot]: time }));
    setEditingSlot(null);
  }

  /** 07 퇴원일과 같은 이유로, 입력칸 아무 곳이나 눌러도 달력이 열리게 합니다. */
  function openDatePicker(event: MouseEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    if (typeof input.showPicker !== 'function') return;
    try {
      input.showPicker();
    } catch {
      // 미지원·제스처 아님 — 기본 동작에 맡깁니다.
    }
  }

  async function persist(
    start: MedicationStartPoint,
    times: MealTimes,
    payloadSlots: Record<number, MealSlot[]>,
  ) {
    if (!schedule) return;
    setSaving(true);
    try {
      await saveMedicationSchedule({
        recordId,
        start,
        mealTimes: times,
        medications: schedule.medications
          .filter((m) => m.timesPerDay !== null)
          .map((m) => ({ medicationId: m.medicationId, slots: payloadSlots[m.medicationId] ?? [] })),
      });
      toast.success('복약 시간을 저장했어요');
      navigate('/dev/flow-complete');
    } finally {
      setSaving(false);
    }
  }

  function handleSave() {
    if (!startSlot || !startDate) return;
    void persist({ date: startDate, slot: startSlot }, mealTimes, slots);
  }

  /** 건너뛰기 — 기본 시각 + 자동 배정 결과를 그대로 보냅니다. */
  function handleSkip() {
    if (!schedule) return;
    const defaults: Record<number, MealSlot[]> = {};
    for (const med of schedule.medications) {
      defaults[med.medicationId] = defaultSlotsFor(med.timesPerDay, med.timing);
    }
    void persist(
      { date: startDate || todayISO(), slot: startSlot ?? 'morning' },
      DEFAULT_MEAL_TIMES,
      defaults,
    );
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

  const scheduledMeds = schedule.medications.filter((m) => m.timesPerDay !== null);
  const usedSlots = new Set<MealSlot>(scheduledMeds.flatMap((m) => slots[m.medicationId] ?? []));
  const orderValid = isMealTimeOrderValid(mealTimes);
  const emptyMedIds = new Set(
    scheduledMeds
      .filter((m) => (slots[m.medicationId] ?? []).length === 0)
      .map((m) => m.medicationId),
  );
  const canSave = Boolean(startSlot) && Boolean(startDate) && orderValid && emptyMedIds.size === 0;

  const editingLabel = editingSlot
    ? MEAL_SLOTS.find((s) => s.value === editingSlot)?.label
    : undefined;

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="복약 시간 설정" onBack={() => navigate(-1)} />

      <main className="flex flex-1 flex-col gap-5 px-page-x py-4">
        {/* [1] 시간대 카드 — 화면의 주인공 */}
        <div className="flex flex-col gap-2">
          <p className="text-base font-bold text-foreground">어느 시간에 알람을 드릴까요?</p>
          <div className="overflow-hidden rounded-card border border-border bg-card">
            {MEAL_SLOTS.map((slot, index) => {
              const unused = !usedSlots.has(slot.value);
              return (
                <button
                  key={slot.value}
                  type="button"
                  onClick={() => setEditingSlot(slot.value)}
                  className={cn(
                    'flex min-h-touch w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-muted-bg',
                    index > 0 && 'border-t border-border',
                  )}
                >
                  <span
                    className={cn(
                      'w-16 shrink-0 text-sm font-bold',
                      unused ? 'text-disabled-foreground' : 'text-foreground',
                    )}
                  >
                    {slot.label}
                  </span>
                  <span
                    className={cn(
                      'text-base',
                      unused ? 'text-disabled-foreground' : 'text-foreground',
                    )}
                  >
                    {mealTimes[slot.value]}
                  </span>
                  {unused && (
                    <span className="text-sm text-disabled-foreground">이 시간에 먹는 약 없음</span>
                  )}
                  <span aria-hidden className="ml-auto text-muted-foreground">
                    ›
                  </span>
                </button>
              );
            })}
          </div>
          {!orderValid && (
            <p className="text-sm text-danger-strong">
              아침약 → 점심약 → 저녁약 → 취침약 순서로 정해주세요.
            </p>
          )}
        </div>

        {/* [2] 복용 시작 시점 — 날짜와 시간대를 직접 고릅니다 */}
        <div className="flex flex-col gap-2">
          <p className="text-base font-bold text-foreground">처음 약을 언제부터 드셨나요?</p>
          <Input
            aria-label="복용 시작 날짜"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            onClick={openDatePicker}
          />
          <div className="flex flex-wrap gap-2">
            {MEAL_SLOTS.map((slot) => {
              const selected = slot.value === startSlot;
              return (
                <button
                  key={slot.value}
                  type="button"
                  aria-pressed={selected}
                  aria-label={`시작 ${slot.label}`}
                  onClick={() => setStartSlot(slot.value)}
                  className={cn(
                    'min-h-touch rounded-pill border px-4 text-sm transition-colors',
                    selected
                      ? 'border-primary bg-primary-bg font-bold text-primary-strong'
                      : 'border-border bg-card text-foreground hover:bg-muted-bg',
                  )}
                >
                  {slot.label}
                </button>
              );
            })}
          </div>
          <p className="text-sm text-muted-foreground">
            {startSlot && startDate
              ? `${formatStartPoint(startDate, startSlot)}부터 복용을 시작한 것으로 기록합니다.`
              : '날짜와 시간을 함께 골라주세요.'}
          </p>
        </div>

        {/* [3] 약별 시간대 */}
        <div className="flex flex-col gap-2">
          <p className="text-base font-bold text-foreground">약마다 언제 먹는지 확인해주세요</p>
          <div className="flex flex-col gap-3">
            {schedule.medications.map((med) => {
              const asNeeded = med.timesPerDay === null;
              const medSlots = slots[med.medicationId] ?? [];
              return (
                <div
                  key={med.medicationId}
                  className="flex flex-col gap-2 rounded-card border border-border bg-card px-4 py-3 shadow-sm"
                >
                  <div className="flex flex-col gap-0.5">
                    <p className="text-base font-bold text-foreground">
                      {med.name} {med.dose}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {asNeeded ? '필요 시' : `1일 ${med.timesPerDay}회 · ${med.timing}`}
                    </p>
                  </div>

                  {asNeeded ? (
                    <p className="border-t border-border pt-2 text-sm text-muted-foreground">
                      필요할 때만 복용 · 알림을 보내지 않아요
                    </p>
                  ) : (
                    <>
                      {/* 4개는 flex-1로 두면 라벨 길이 차이로 폭이 들쭉날쭉해집니다. */}
                      <div className="grid grid-cols-4 gap-2 border-t border-border pt-2">
                        {MEAL_SLOTS.map((slot) => {
                          const on = medSlots.includes(slot.value);
                          return (
                            <button
                              key={slot.value}
                              type="button"
                              aria-pressed={on}
                              aria-label={`${med.name} ${slot.label}`}
                              onClick={() => toggleSlot(med.medicationId, slot.value)}
                              className={cn(
                                'h-touch rounded-input border text-sm transition-colors',
                                on
                                  ? 'border-primary bg-primary font-bold text-card'
                                  : 'border-border bg-card text-muted-foreground hover:bg-muted-bg',
                              )}
                            >
                              {slot.short}
                            </button>
                          );
                        })}
                      </div>

                      {emptyMedIds.has(med.medicationId) && (
                        <p className="text-sm text-danger-strong">
                          복용 시간을 하나 이상 선택해주세요.
                        </p>
                      )}

                      {exceedsSlotCapacity(med.timesPerDay) && (
                        <p className="text-sm text-warning-strong">
                          1일 {med.timesPerDay}회 처방이에요. 시간 4개로는 다 담기지 않아 복용
                          간격을 의료진·약사에게 확인해주세요.
                        </p>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <p className="text-sm text-muted-foreground">
          저장한 시간에 알림을 보내요. 나중에 마이페이지에서 바꿀 수 있어요.
        </p>

        <div className="flex-1" />

        <div className="flex flex-col gap-2 pb-4">
          <Button onClick={handleSave} disabled={saving || !canSave}>
            {saving ? '저장 중...' : '저장하고 계속'}
          </Button>
          <Button variant="secondary" onClick={handleSkip} disabled={saving}>
            기본 시간으로 건너뛰기
          </Button>
        </div>
      </main>

      <TimePickerSheet
        open={editingSlot !== null}
        description={editingLabel ? `${editingLabel} 알림 시각` : ''}
        value={editingSlot ? mealTimes[editingSlot] : '08:00'}
        onApply={applyTime}
        onCancel={() => setEditingSlot(null)}
      />
    </div>
  );
}
