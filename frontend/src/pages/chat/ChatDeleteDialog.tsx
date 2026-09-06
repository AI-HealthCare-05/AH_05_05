import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui';

interface ChatDeleteDialogProps {
  open: boolean;
  count: number;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ChatDeleteDialog({
  open,
  count,
  deleting,
  onCancel,
  onConfirm,
}: ChatDeleteDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && !deleting && onCancel()}>
      <DialogContent
        showCloseButton={false}
        className="w-[calc(100%-2.5rem)] max-w-[350px] rounded-card p-5"
      >
        <DialogHeader>
          <DialogTitle>선택한 대화를 삭제할까요?</DialogTitle>
          <DialogDescription>
            선택한 {count}개 대화는 목록에서 다시 볼 수 없어요.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="danger" disabled={deleting} onClick={onConfirm}>
            삭제
          </Button>
          <Button variant="secondary" disabled={deleting} onClick={onCancel}>
            취소
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
