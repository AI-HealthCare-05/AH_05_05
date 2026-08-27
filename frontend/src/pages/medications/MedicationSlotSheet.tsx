import { useEffect, useState } from 'react';
import type { MealSlot, MedicationOverviewItem } from '@/entities/medication';
import { cn } from '@/shared/lib/cn';
import { MEAL_SLOTS, SLOT_ORDER } from '@/shared/model/mealSlot';
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle } from '@/shared/ui';

interface MedicationSlotSheetProps {
  open: boolean;
  medication: MedicationOverviewItem | null;
  onOpenChange: (open: boolean) => void;
  onSave: (slots: MealSlot[]) => Promise<void>;
}

export function MedicationSlotSheet({
  open,
  medication,
  onOpenChange,
  onSave,
}: MedicationSlotSheetProps) {
  const [selectedSlots, setSelectedSlots] = useState<MealSlot[]>(medication?.slots ?? []);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setSelectedSlots(medication?.slots ?? []);
  }, [medication, open]);

  function toggleSlot(slot: MealSlot) {
    const next = new Set(selectedSlots);
    if (next.has(slot)) next.delete(slot);
    else next.add(slot);
    setSelectedSlots(SLOT_ORDER.filter((item) => next.has(item)));
  }

  async function save() {
    if (selectedSlots.length === 0 || saving) return;
    setSaving(true);
    try {
      await onSave(selectedSlots);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" aria-describedby="medication-slot-description">
        <div className="pr-10">
          <DialogTitle className="text-xl">{medication?.name ?? '약'} 복용 시간</DialogTitle>
          <DialogDescription id="medication-slot-description" className="mt-1">
            이 약을 먹는 시간대를 골라주세요.
          </DialogDescription>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {MEAL_SLOTS.map((slot) => {
            const selected = selectedSlots.includes(slot.value);
            return (
              <button
                key={slot.value}
                type="button"
                aria-pressed={selected}
                aria-label={`${medication?.name ?? '약'} ${slot.label}`}
                className={cn(
                  'min-h-touch rounded-input border text-sm font-bold',
                  selected
                    ? 'border-primary bg-primary text-card'
                    : 'border-border bg-card text-muted-foreground',
                )}
                onClick={() => toggleSlot(slot.value)}
              >
                {slot.label}
              </button>
            );
          })}
        </div>
        {selectedSlots.length === 0 && (
          <p className="text-sm text-danger-strong">복용 시간을 하나 이상 선택해주세요.</p>
        )}
        <Button disabled={selectedSlots.length === 0 || saving} onClick={() => void save()}>
          {saving ? '저장 중...' : '저장'}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
