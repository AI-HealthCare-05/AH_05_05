import type { FollowUpVisit } from '@/entities/follow-up-visit';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui';

interface DeleteFollowUpVisitDialogProps {
  visit: FollowUpVisit | null;
  deleting: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function DeleteFollowUpVisitDialog({
  visit,
  deleting,
  onOpenChange,
  onConfirm,
}: DeleteFollowUpVisitDialogProps) {
  return (
    <Dialog open={visit !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>진료일정 삭제</DialogTitle>
          <DialogDescription>
            이 일정을 삭제하면 연결된 알림도 함께 삭제돼요.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="grid grid-cols-2 gap-2">
          <Button variant="secondary" disabled={deleting} onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button variant="danger" disabled={deleting} onClick={onConfirm}>
            {deleting ? '삭제 중...' : '삭제하기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
