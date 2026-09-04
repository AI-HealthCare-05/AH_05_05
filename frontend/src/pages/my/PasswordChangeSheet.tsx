import { useEffect, useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { changePassword, type ChangePasswordPayload } from '@/entities/account';
import { ApiError } from '@/shared/api/client';
import { PASSWORD_MAX_LENGTH } from '@/shared/lib/password';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Input,
} from '@/shared/ui';

/** 오류 문구를 어느 칸 아래에 붙일지. 칸을 특정할 수 없으면 폼 전체에 띄웁니다. */
type ErrorTarget = 'current' | 'new' | 'form';

/**
 * 서버 오류를 해당 입력칸으로 보냅니다.
 *
 * 예전에는 전부 「현재 비밀번호」 아래에 붙어서, 새 비밀번호 정책 위반인데도
 * 엉뚱한 칸이 빨갛게 됐습니다.
 *
 * 422 는 서버가 `field` 를 실어 보냅니다(exception_handlers 가 loc 에서 뽑습니다).
 * 400 은 `field` 가 없어 code 로 가릅니다.
 *
 * `field` 는 **보낸 표기법을 그대로 되돌려줍니다.** 지금은 camelCase 로 보내지만,
 * 서버가 두 표기법을 모두 받으므로(populate_by_name) 양쪽을 다 봅니다.
 */
function errorTarget(error: unknown): ErrorTarget {
  if (!(error instanceof ApiError)) return 'form';
  if (error.field === 'newPassword' || error.field === 'new_password') return 'new';
  if (error.field === 'currentPassword' || error.field === 'current_password') return 'current';
  if (error.code === 'SAME_AS_CURRENT') return 'new';
  if (error.code === 'INVALID_PASSWORD') return 'current';
  // 네트워크 오류나 5xx 처럼 특정 칸의 문제가 아닌 것들.
  return 'form';
}

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
  const [newPasswordError, setNewPasswordError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function clearErrors() {
    setCurrentPasswordError(null);
    setNewPasswordError(null);
    setConfirmError(null);
    setFormError(null);
  }

  useEffect(() => {
    if (open) return;
    setCurrentPassword('');
    setNewPassword('');
    setNewPasswordConfirm('');
    clearErrors();
    setSaving(false);
  }, [open]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearErrors();
    if (newPassword !== newPasswordConfirm) {
      setConfirmError('새 비밀번호가 일치하지 않아요.');
      return;
    }

    setSaving(true);
    try {
      await passwordChanger({ currentPassword, newPassword });
      onOpenChange(false);
      toast.success('비밀번호를 변경했어요.');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : '비밀번호를 변경하지 못했어요.';
      const target = errorTarget(error);
      if (target === 'current') setCurrentPasswordError(message);
      else if (target === 'new') setNewPasswordError(message);
      else setFormError(message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        variant="sheet"
        aria-describedby="password-change-description"
        className="max-h-[90dvh] overflow-y-auto"
      >
        <div aria-hidden className="mx-auto h-1 w-10 rounded-pill bg-border" />
        <div className="flex flex-col gap-1 pt-2">
          <DialogTitle className="text-xl">비밀번호 변경</DialogTitle>
          <DialogDescription id="password-change-description">
            현재 비밀번호를 확인한 뒤 새 비밀번호로 바꿉니다.
          </DialogDescription>
        </div>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <Input
            label="현재 비밀번호"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            // 여기에는 maxLength 를 걸지 않습니다. 대조용으로 받는 값이라, 이 정책이
            // 생기기 전에 더 긴 비밀번호로 가입한 사람이 비밀번호를 영영 못 바꾸게 됩니다.
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
            maxLength={PASSWORD_MAX_LENGTH}
            error={newPasswordError ?? undefined}
            onChange={(event) => {
              setNewPassword(event.target.value);
              setNewPasswordError(null);
            }}
            required
          />
          <Input
            label="새 비밀번호 확인"
            type="password"
            autoComplete="new-password"
            value={newPasswordConfirm}
            maxLength={PASSWORD_MAX_LENGTH}
            error={confirmError ?? undefined}
            onChange={(event) => {
              setNewPasswordConfirm(event.target.value);
              setConfirmError(null);
            }}
            required
          />
          {/* 특정 칸의 문제가 아닌 오류(네트워크·5xx)는 버튼 위에 띄웁니다. */}
          {formError && (
            <p role="alert" className="text-sm text-danger-strong">
              {formError}
            </p>
          )}
          <Button type="submit" disabled={saving}>변경</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
