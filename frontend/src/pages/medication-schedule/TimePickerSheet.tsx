import { useEffect, useState } from 'react';
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
import { HOUR_OPTIONS, MINUTE_OPTIONS } from './timePresets';

/**
 * `09-A 시간 선택` (Figma node 114:11)의 하단 시트.
 *
 * Figma는 시·분 휠(스크롤 피커)로 그려져 있지만, REQ-CARE-003이 "시·분 선택 박스
 * (30분 단위, 00분·30분만 선택)"라고 정하고 있어 Select로 구현했습니다.
 *
 * 현재 저장된 시각으로 시작하고, 사용자가 시·분을 직접 고릅니다.
 */

export interface TimePickerSheetProps {
  open: boolean;
  /** 시트 부제. 예: "셀레콕시브 200mg · 2번째 복용 시각" */
  description: string;
  /** 현재 슬롯에 들어있는 시각(HH:MM). */
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

  // 열릴 때마다 현재 슬롯 값으로 초기화합니다.
  useEffect(() => {
    if (!open) return;
    const [h, m] = value.split(':');
    setHour(h ?? '08');
    setMinute(m === '30' ? '30' : '00');
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
              {HOUR_OPTIONS.map((h) => (
                <SelectItem key={h} value={h}>
                  {h}시
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
              {MINUTE_OPTIONS.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}분
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
