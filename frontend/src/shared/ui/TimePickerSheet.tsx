import { useEffect, useState } from 'react';
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
import { HOUR_OPTIONS, MINUTE_OPTIONS } from './timePickerOptions';

export interface TimePickerSheetProps {
  open: boolean;
  description: string;
  value: string;
  onApply: (time: string) => void;
  onCancel: () => void;
}

export function TimePickerSheet({
  open,
  description,
  value,
  onApply,
  onCancel,
}: TimePickerSheetProps) {
  const [hour, setHour] = useState('08');
  const [minute, setMinute] = useState('00');

  useEffect(() => {
    if (!open) return;
    const [nextHour, nextMinute] = value.split(':');
    setHour(nextHour ?? '08');
    setMinute(nextMinute === '30' ? '30' : '00');
  }, [open, value]);

  const current = `${hour}:${minute}`;

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent
        showCloseButton={false}
        className="top-auto bottom-0 w-full max-w-app translate-y-0 rounded-b-none"
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
            <SelectTrigger aria-label="분">
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

        <p className="text-sm text-muted-foreground">
          분은 00분 또는 30분 단위로 선택할 수 있어요.
        </p>

        <DialogFooter>
          <Button onClick={() => onApply(current)}>이 시간 적용</Button>
          <Button variant="secondary" onClick={onCancel}>
            취소
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
