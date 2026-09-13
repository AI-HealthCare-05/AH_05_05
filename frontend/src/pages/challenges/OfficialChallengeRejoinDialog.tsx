import { Button } from '@/shared/ui/Button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog';

export function OfficialChallengeRejoinDialog({ open, pending, onOpenChange, onConfirm }: {
  open: boolean;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={value => { if (!pending) onOpenChange(value); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>챌린지에 다시 참여할까요?</DialogTitle>
          <DialogDescription>이전 기록은 보관돼요. 다시 참여하면 수행 기간이 오늘부터 새로 시작되고, 진행률은 0%부터 쌓아요.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button disabled={pending} onClick={onConfirm}>{pending ? '참여 중' : '다시 참여하기'}</Button>
          <Button variant="secondary" disabled={pending} onClick={() => onOpenChange(false)}>돌아가기</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
