import { useEffect, useState } from 'react';
import { withdrawAccount, type WithdrawAccountPayload } from '@/entities/account';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
} from '@/shared/ui';

interface WithdrawAccountDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onWithdrawn: () => void;
  accountWithdrawer?: (payload: WithdrawAccountPayload) => Promise<void>;
}

export function WithdrawAccountDialog({
  open,
  onOpenChange,
  onWithdrawn,
  accountWithdrawer = withdrawAccount,
}: WithdrawAccountDialogProps) {
  const [password, setPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) return;
    setPassword('');
    setPasswordError(null);
    setSubmitting(false);
  }, [open]);

  async function confirmWithdrawal() {
    if (!password || submitting) return;
    setSubmitting(true);
    setPasswordError(null);
    try {
      await accountWithdrawer({ password });
      onOpenChange(false);
      onWithdrawn();
    } catch (error: unknown) {
      setPasswordError(
        error instanceof Error ? error.message : '회원 탈퇴를 처리하지 못했어요.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby="withdraw-account-description"
        className="max-h-[calc(100dvh-2rem)] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>정말 탈퇴하시겠어요?</DialogTitle>
          {/*
            예전 문구는 "같은 이메일로 다시 가입할 수 있다"였는데 사실이 아닙니다.
            탈퇴해도 user 행이 남아 회원가입의 중복 검사에 걸립니다.
            되돌릴 수 없는 동작이라 누르기 전에 알아야 합니다.
          */}
          <DialogDescription id="withdraw-account-description">
            복약 기록과 등록한 영양제를 다시 볼 수 없어요.
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-input bg-danger-bg p-3">
          <p className="text-sm font-bold leading-relaxed text-danger-strong">
            탈퇴하면 같은 이메일로 다시 가입할 수 없어요.
          </p>
        </div>
        <Input
          label="비밀번호"
          type="password"
          autoComplete="current-password"
          value={password}
          // maxLength 를 걸지 않습니다. 대조용으로 받는 값이라, 비밀번호 상한이 생기기 전에
          // 더 긴 비밀번호로 가입한 사람이 탈퇴 자체를 못 하게 됩니다.
          // 서버 WithdrawRequest 가 validate_password 를 안 붙이는 것과 같은 이유입니다.
          error={passwordError ?? undefined}
          onChange={(event) => {
            setPassword(event.target.value);
            setPasswordError(null);
          }}
        />
        <DialogFooter className="grid grid-cols-2 gap-2">
          <Button type="button" onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={!password || submitting}
            onClick={() => void confirmWithdrawal()}
          >
            {submitting ? '처리 중...' : '탈퇴하기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
