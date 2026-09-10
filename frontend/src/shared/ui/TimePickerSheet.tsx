import { useEffect, useId, useState } from 'react';
import { Button } from './Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './select';
import {
  getMinuteOptions,
  HOUR_OPTIONS,
  type MinuteStep,
} from './timePickerOptions';

export interface TimePickerSheetProps {
  open: boolean;
  description: string;
  value: string;
  minuteStep?: MinuteStep;
  preserveInvalidMinute?: boolean;
  onApply: (time: string) => void;
  onCancel: () => void;
}

export function TimePickerSheet({
  open,
  description,
  value,
  minuteStep = 30,
  preserveInvalidMinute = false,
  onApply,
  onCancel,
}: TimePickerSheetProps) {
  const [hour, setHour] = useState('08');
  const [minute, setMinute] = useState('00');
  const minuteHelpId = useId();
  const minuteOptions = getMinuteOptions(minuteStep);

  useEffect(() => {
    if (!open) return;
    const [nextHour, nextMinute] = value.split(':');
    setHour(nextHour ?? '08');
    setMinute(
      preserveInvalidMinute && /^\d{2}$/.test(nextMinute ?? '')
        ? nextMinute
        : minuteOptions.includes(nextMinute ?? '')
          ? nextMinute
          : minuteOptions[0],
    );
  }, [open, preserveInvalidMinute, value, minuteStep]);

  const current = `${hour}:${minute}`;
  const minuteIsValid = minuteOptions.includes(minute);

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent
        showCloseButton={false}
        className="top-auto bottom-0 w-full max-w-dialog translate-y-0 rounded-b-none"
      >
        <DialogHeader>
          <DialogTitle>시간 선택</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2">
          <Select value={hour} onValueChange={setHour}>
            <SelectTrigger aria-label="시">
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
          <Select value={minute} onValueChange={setMinute}>
            <SelectTrigger
              aria-label="분"
              aria-invalid={!minuteIsValid ? true : undefined}
              aria-describedby={minuteHelpId}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {!minuteIsValid && preserveInvalidMinute && (
                <SelectItem value={minute} disabled>
                  {minute}분 (기존 값)
                </SelectItem>
              )}
              {minuteOptions.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}분
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <p id={minuteHelpId} className="text-sm text-muted-foreground">
          {minuteIsValid
            ? minuteStep === 30
              ? '분은 00분 또는 30분 단위로 선택할 수 있어요.'
              : `분은 ${minuteStep}분 단위로 선택할 수 있어요.`
            : `현재 저장된 ${value}은 ${minuteStep}분 단위가 아니에요.`}
        </p>

        <DialogFooter>
          <Button disabled={!minuteIsValid} onClick={() => onApply(current)}>
            이 시간 적용
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            취소
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
