import { Button } from './Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './dialog';

export interface NotifyBlockedDialogProps {
  open: boolean;
  onConfirm: () => void;
}

export function NotifyBlockedDialog({ open, onConfirm }: NotifyBlockedDialogProps) {
  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>알림이 차단되어 있어요</DialogTitle>
          <DialogDescription>
            브라우저에서 이 사이트의 알림을 차단해두셨어요. 주소창 왼쪽 자물쇠(또는 ⓘ) →
            알림 → 허용으로 바꾸시면 켤 수 있어요.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={onConfirm}>확인</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
