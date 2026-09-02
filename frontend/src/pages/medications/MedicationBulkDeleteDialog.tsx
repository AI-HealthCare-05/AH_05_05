import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from '@/shared/ui';

interface MedicationBulkDeleteDialogProps {
  open: boolean;
  count: number;
  pending: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  onRetry: () => void;
}

export function MedicationBulkDeleteDialog({
  open,
  count,
  pending,
  error,
  onOpenChange,
  onConfirm,
  onRetry,
}: MedicationBulkDeleteDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent showCloseButton={!pending}>
        <DialogTitle>
          {error ? '복약 정보를 삭제하지 못했어요' : `${count}개를 삭제할까요?`}
        </DialogTitle>
        <DialogDescription>
          {error ?? '삭제한 처방은 약봉투를 다시 등록해야 복구할 수 있어요.'}
        </DialogDescription>
        <DialogFooter>
          {error ? (
            <Button disabled={pending} onClick={onRetry}>
              {pending ? '다시 시도 중...' : '다시 시도'}
            </Button>
          ) : (
            <Button variant="danger" disabled={pending} onClick={onConfirm}>
              {pending ? '삭제 중...' : '삭제하기'}
            </Button>
          )}
          <Button variant="secondary" disabled={pending} onClick={() => onOpenChange(false)}>
            취소
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
