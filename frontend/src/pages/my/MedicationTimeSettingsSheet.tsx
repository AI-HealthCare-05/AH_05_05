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
          <DialogTitle>알림 시간 설정</DialogTitle>
          <div className="flex flex-col gap-1 pt-2">
            <h2 className="text-2xl font-bold text-foreground">언제 알려드릴까요?</h2>
            <DialogDescription>식사 시간에 맞춰 자유롭게 바꿀 수 있어요.</DialogDescription>
          </div>
        </DialogHeader>

        <div className="overflow-hidden rounded-card border border-border bg-card">
          {MEAL_SLOTS.map((slot, index) => {
            const label = TIME_LABELS[slot.value];
            const field = SETTINGS_FIELD_BY_SLOT[slot.value];
            const [hour = '00', minute = '00'] = values[field].split(':');

            return (
              <div
                key={slot.value}
                className={`flex min-h-16 items-center gap-2 px-4 ${
                  index > 0 ? 'border-t border-border' : ''
                }`}
              >
                <span className="flex-1 text-[15px] font-bold text-foreground">{label}</span>
                <div className="flex items-center gap-1">
                  <Select
                    value={hour}
                    onValueChange={(nextHour) =>
                      changeTime(slot.value, 'hour', nextHour)
                    }
                  >
                    <SelectTrigger
                      aria-label={`${label} 시`}
                      className="h-11 w-[4.5rem] justify-end border-0 bg-transparent px-0 text-right shadow-none [&>svg]:hidden"
                    >
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
                  <span aria-hidden className="text-base text-muted-foreground">
                    :
                  </span>
                  <Select
                    value={minute}
                    onValueChange={(nextMinute) =>
                      changeTime(slot.value, 'minute', nextMinute)
                    }
                  >
                    <SelectTrigger
                      aria-label={`${label} 분`}
                      className="h-11 w-[4.5rem] justify-start border-0 bg-transparent px-0 text-left shadow-none [&>svg]:hidden"
                    >
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
                  <span aria-hidden className="text-xl text-muted-foreground">›</span>
                </div>
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
