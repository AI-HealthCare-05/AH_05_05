import { useEffect, useRef, useState } from 'react';
import { Minus, Plus } from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import { MEAL_SLOTS, SLOT_ORDER, type MealSlot } from '@/shared/model/mealSlot';

const MIN_DAILY_COUNT = 1;
const MAX_DAILY_COUNT = 20;
const ADJUSTMENT_NOTICE_MS = 1800;

export interface DoseSlotFieldsProps {
  dailyCount: number;
  slots: MealSlot[];
  onDailyCountChange: (dailyCount: number) => void;
  onSlotsChange: (slots: MealSlot[]) => void;
}

export function DoseSlotFields({
  dailyCount,
  slots,
  onDailyCountChange,
  onSlotsChange,
}: DoseSlotFieldsProps) {
  const [adjustmentNotice, setAdjustmentNotice] = useState<string | null>(null);
  const noticeTimerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (noticeTimerRef.current !== null) window.clearTimeout(noticeTimerRef.current);
    },
    [],
  );

  function announceAdjustment(nextDailyCount: number) {
    if (noticeTimerRef.current !== null) window.clearTimeout(noticeTimerRef.current);
    setAdjustmentNotice(`하루 ${nextDailyCount}정으로 맞췄어요`);
    noticeTimerRef.current = window.setTimeout(() => {
      setAdjustmentNotice(null);
      noticeTimerRef.current = null;
    }, ADJUSTMENT_NOTICE_MS);
  }

  function toggleSlot(slot: MealSlot) {
    const selected = new Set(slots);
    if (selected.has(slot)) selected.delete(slot);
    else selected.add(slot);
    const nextSlots = SLOT_ORDER.filter((item) => selected.has(item));
    onSlotsChange(nextSlots);
    if (nextSlots.length > dailyCount) {
      onDailyCountChange(nextSlots.length);
      announceAdjustment(nextSlots.length);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-base text-muted-foreground">하루에</span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="하루 섭취량 줄이기"
            disabled={dailyCount <= Math.max(MIN_DAILY_COUNT, slots.length)}
            onClick={() => onDailyCountChange(Math.max(MIN_DAILY_COUNT, dailyCount - 1))}
            className="flex size-touch items-center justify-center rounded-pill border border-border text-foreground disabled:text-disabled-foreground"
          >
            <Minus aria-hidden className="size-5" />
          </button>
          <strong className="min-w-12 text-center text-xl font-bold text-foreground tnum">
            {dailyCount} 정
          </strong>
          <button
            type="button"
            aria-label="하루 섭취량 늘리기"
            disabled={dailyCount >= MAX_DAILY_COUNT}
            onClick={() => onDailyCountChange(Math.min(MAX_DAILY_COUNT, dailyCount + 1))}
            className="flex size-touch items-center justify-center rounded-pill border border-border text-foreground disabled:text-disabled-foreground"
          >
            <Plus aria-hidden className="size-5" />
          </button>
        </div>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-base font-bold text-foreground">언제 드세요?</legend>
        <div role="group" aria-label="복용 시간" className="grid grid-cols-4 gap-2">
          {MEAL_SLOTS.map((slot) => {
            const selected = slots.includes(slot.value);
            return (
              <button
                key={slot.value}
                type="button"
                aria-pressed={selected}
                className={cn(
                  'min-h-touch rounded-input border px-1 text-sm font-bold',
                  selected
                    ? 'border-primary bg-primary text-card'
                    : 'border-border bg-card text-muted-foreground',
                )}
                onClick={() => toggleSlot(slot.value)}
              >
                {slot.short}
              </button>
            );
          })}
        </div>
      </fieldset>

      <p aria-live="polite" className="min-h-5 text-sm text-muted-foreground">
        {adjustmentNotice}
      </p>
    </div>
  );
}
