import { SLOT_ORDER, mealSlotLabel } from '@/shared/model/mealSlot';
import { Button } from './Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './dialog';

interface NotifyMealTimes {
  morning: string;
  lunch: string;
  evening: string;
  bedtime: string;
}

export interface NotifyPermissionDialogProps {
  open: boolean;
  mealTimes?: NotifyMealTimes;
  title?: string;
  busy?: boolean;
  onAccept: () => void;
  onDismiss: () => void;
}

export function NotifyPermissionDialog({
  open,
  mealTimes,
  title = '복약 시간에 알림을 보내드릴까요?',
  busy = false,
  onAccept,
  onDismiss,
}: NotifyPermissionDialogProps) {
  const timeSummary = mealTimes
    ? SLOT_ORDER.map((slot) => `${mealSlotLabel(slot, 'short')} ${mealTimes[slot]}`).join(' · ')
    : null;

  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="flex flex-col gap-1">
            {timeSummary && <span className="font-medium text-foreground">{timeSummary}</span>}
            <span>
              {mealTimes
                ? '방금 정하신 시각에 맞춰 알려드려요.'
                : '선택하신 알림을 이 기기로 보내드려요.'}
            </span>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="grid grid-cols-2">
          <Button variant="secondary" disabled={busy} onClick={onDismiss}>
            나중에
          </Button>
          <Button disabled={busy} onClick={onAccept}>
            {busy ? '확인 중...' : '좋아요'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
