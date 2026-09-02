import type { MedicationTimes } from '@/entities/settings';
import { MEAL_SLOTS, type MealSlot } from '@/shared/model/mealSlot';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui';
import { HOUR_OPTIONS, MINUTE_OPTIONS } from '@/shared/ui/timePickerOptions';

const SETTINGS_FIELD_BY_SLOT: Record<MealSlot, keyof MedicationTimes> = {
  morning: 'morningMedicationTime',
  lunch: 'lunchMedicationTime',
  evening: 'eveningMedicationTime',
  bedtime: 'bedtimeMedicationTime',
};

const TIME_LABELS: Record<MealSlot, string> = {
  morning: '아침',
  lunch: '점심',
  evening: '저녁',
  bedtime: '자기전',
};

interface MedicationTimeSettingsSheetProps {
  open: boolean;
  values: MedicationTimes;
  busy: boolean;
  error: string | null;
  onChange: (values: MedicationTimes) => void;
  onSave: () => void;
  onCancel: () => void;
}

function replaceTimePart(
  value: string,
  part: 'hour' | 'minute',
  nextPart: string,
): string {
  const [hour = '00', minute = '00'] = value.split(':');
  return part === 'hour' ? `${nextPart}:${minute}` : `${hour}:${nextPart}`;
}

export function MedicationTimeSettingsSheet({
  open,
  values,
  busy,
  error,
  onChange,
  onSave,
  onCancel,
}: MedicationTimeSettingsSheetProps) {
  function changeTime(slot: MealSlot, part: 'hour' | 'minute', nextPart: string) {
    const field = SETTINGS_FIELD_BY_SLOT[slot];
    onChange({
      ...values,
      [field]: replaceTimePart(values[field], part, nextPart),
    });
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => (nextOpen ? undefined : onCancel())}>
      <DialogContent variant="sheet" className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>알림 시간</DialogTitle>
          <DialogDescription className="sr-only">
            복약 알림을 받을 시간을 설정해 주세요.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {MEAL_SLOTS.map((slot) => {
            const label = TIME_LABELS[slot.value];
            const field = SETTINGS_FIELD_BY_SLOT[slot.value];
            const [hour = '00', minute = '00'] = values[field].split(':');

            return (
              <div
                key={slot.value}
                className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2"
              >
                <span className="text-base font-bold text-foreground">{label}</span>
                <Select
                  value={hour}
                  onValueChange={(nextHour) =>
                    changeTime(slot.value, 'hour', nextHour)
                  }
                >
                  <SelectTrigger aria-label={`${label} 시`} className="min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {HOUR_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}시
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <span aria-hidden className="text-lg font-bold text-foreground">
                  :
                </span>
                <Select
                  value={minute}
                  onValueChange={(nextMinute) =>
                    changeTime(slot.value, 'minute', nextMinute)
                  }
                >
                  <SelectTrigger aria-label={`${label} 분`} className="min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MINUTE_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}분
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            );
          })}
        </div>

        {error && (
          <p role="alert" className="text-sm font-bold text-danger-strong">
            {error}
          </p>
        )}

        <DialogFooter className="grid grid-cols-2 gap-3 pt-2">
          <Button variant="secondary" disabled={busy} onClick={onCancel}>
            취소
          </Button>
          <Button disabled={busy} onClick={onSave}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
