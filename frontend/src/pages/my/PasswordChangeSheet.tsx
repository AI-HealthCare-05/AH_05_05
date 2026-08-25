import { useEffect, useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { changePassword, type ChangePasswordPayload } from '@/entities/account';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Input,
} from '@/shared/ui';

interface PasswordChangeSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  passwordChanger?: (payload: ChangePasswordPayload) => Promise<void>;
}

export function PasswordChangeSheet({
  open,
  onOpenChange,
  passwordChanger = changePassword,
}: PasswordChangeSheetProps) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('');
  const [currentPasswordError, setCurrentPasswordError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) return;
    setCurrentPassword('');
    setNewPassword('');
    setNewPasswordConfirm('');
    setCurrentPasswordError(null);
    setConfirmError(null);
    setSaving(false);
  }, [open]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCurrentPasswordError(null);
    if (newPassword !== newPasswordConfirm) {
      setConfirmError('새 비밀번호가 일치하지 않아요.');
      return;
    }

    setConfirmError(null);
    setSaving(true);
    try {
      await passwordChanger({ currentPassword, newPassword });
      onOpenChange(false);
      toast.success('비밀번호를 변경했어요.');
    } catch (error: unknown) {
      setCurrentPasswordError(
        error instanceof Error ? error.message : '비밀번호를 변경하지 못했어요.',
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" aria-describedby="password-change-description">
        <div aria-hidden className="mx-auto h-1 w-10 rounded-pill bg-border" />
        <div className="flex flex-col gap-1 pt-2">
          <DialogTitle className="text-xl">비밀번호 변경</DialogTitle>
          <DialogDescription id="password-change-description">
            현재 비밀번호를 확인한 뒤 새 비밀번호로 바꿉니다.
          </DialogDescription>
        </div>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <Input
            label="현재 비밀번호"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            error={currentPasswordError ?? undefined}
            onChange={(event) => {
              setCurrentPassword(event.target.value);
              setCurrentPasswordError(null);
            }}
            required
          />
          <Input
            label="새 비밀번호"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            required
          />
          <Input
            label="새 비밀번호 확인"
            type="password"
            autoComplete="new-password"
            value={newPasswordConfirm}
            error={confirmError ?? undefined}
            onChange={(event) => {
              setNewPasswordConfirm(event.target.value);
              setConfirmError(null);
            }}
            required
          />
          <Button type="submit" disabled={saving}>변경</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
