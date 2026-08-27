import { Minus, Plus } from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import { MEAL_SLOTS, SLOT_ORDER, type MealSlot } from '@/shared/model/mealSlot';

const MAX_DOSE_AMOUNT = 99_999.999;

export interface DoseSlotFieldsProps {
  doseAmount: number;
  doseUnit: string;
  doseStep?: number;
  slots: MealSlot[];
  onDoseAmountChange: (doseAmount: number) => void;
  onSlotsChange: (slots: MealSlot[]) => void;
}

export function DoseSlotFields({
  doseAmount,
  doseUnit,
  doseStep = 1,
  slots,
  onDoseAmountChange,
  onSlotsChange,
}: DoseSlotFieldsProps) {
  const step = Number.isFinite(doseStep) && doseStep > 0 ? doseStep : 1;

  function toggleSlot(slot: MealSlot) {
    const selected = new Set(slots);
    if (selected.has(slot)) selected.delete(slot);
    else selected.add(slot);
    const nextSlots = SLOT_ORDER.filter((item) => selected.has(item));
    onSlotsChange(nextSlots);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-base text-muted-foreground">1회에</span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="1회 섭취량 줄이기"
            disabled={doseAmount <= step}
            onClick={() => onDoseAmountChange(adjustDoseAmount(doseAmount, -step, step))}
            className="flex size-touch items-center justify-center rounded-pill border border-border text-foreground disabled:text-disabled-foreground"
          >
            <Minus aria-hidden className="size-5" />
          </button>
          <strong className="min-w-12 text-center text-xl font-bold text-foreground tnum">
            {doseAmount} {doseUnit}
          </strong>
          <button
            type="button"
            aria-label="1회 섭취량 늘리기"
            disabled={doseAmount >= MAX_DOSE_AMOUNT}
            onClick={() => onDoseAmountChange(adjustDoseAmount(doseAmount, step, step))}
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

      <p aria-live="polite" className="min-h-5 text-sm text-danger-strong">
        {slots.length === 0 ? '복용 시간을 하나 이상 선택해주세요.' : null}
      </p>
    </div>
  );
}

function adjustDoseAmount(amount: number, delta: number, minimum: number): number {
  const next = Math.min(MAX_DOSE_AMOUNT, Math.max(minimum, amount + delta));
  return Math.round(next * 1_000) / 1_000;
}
