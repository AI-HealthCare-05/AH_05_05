import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui';

interface MedicationCancelDialogProps {
  open: boolean;
  pending: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function MedicationCancelDialog({
  open,
  pending,
  error,
  onOpenChange,
  onConfirm,
}: MedicationCancelDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!pending) onOpenChange(nextOpen);
      }}
    >
      <DialogContent
        showCloseButton={false}
        aria-describedby="medication-cancel-description"
      >
        <DialogHeader>
          <DialogTitle>이 복약 정보를 삭제할까요?</DialogTitle>
          <DialogDescription id="medication-cancel-description">
            홈과 복약 탭에서 사라져요. 다시 등록하려면 약봉투를 다시 찍어야 해요.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <p role="alert" className="rounded-input bg-danger-bg px-3 py-2 text-sm text-danger-strong">
            {error}
          </p>
        )}

        <DialogFooter className="grid grid-cols-2 gap-2 pt-1">
          <Button disabled={pending} onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button variant="danger" disabled={pending} onClick={onConfirm}>
            {pending ? '삭제 중...' : '삭제하기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
