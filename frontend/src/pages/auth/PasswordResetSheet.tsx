import { useRef, useState, type FormEvent } from 'react';
import { requestPasswordReset } from '@/entities/auth';
import { EMAIL_INPUT_PATTERN, EMAIL_MAX_LENGTH, sanitizeEmailInput } from '@/shared/lib/email';
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle, Input } from '@/shared/ui';
import './password-reset-sheet.css';

interface PasswordResetSheetProps {
  initialEmail: string;
  onClose: () => void;
  onRestoreFocus: () => void;
}

export function PasswordResetSheet({ initialEmail, onClose, onRestoreFocus }: PasswordResetSheetProps) {
  const [email, setEmail] = useState(() => sanitizeEmailInput(initialEmail));
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestPending = useRef(false);

  function close() {
    if (!requestPending.current) onClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (requestPending.current || sent || !event.currentTarget.reportValidity()) return;
    requestPending.current = true;
    setSending(true);
    setError(null);
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch {
      setError('발송을 요청하지 못했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      requestPending.current = false;
      setSending(false);
    }
  }

  return (
    <Dialog open onOpenChange={open => { if (!open) close(); }}>
      <DialogContent
        variant="sheet"
        className="password-reset-sheet max-h-[90dvh] overflow-y-auto motion-safe:animate-[password-reset-open_240ms_ease-out]"
        onCloseAutoFocus={event => {
          event.preventDefault();
          onRestoreFocus();
        }}
      >
        <div aria-hidden className="mx-auto h-1 w-10 rounded-pill bg-border" />
        <div className="flex flex-col gap-2 pt-2">
          <DialogTitle className="text-xl">비밀번호 재설정</DialogTitle>
          {!sent && (
            <DialogDescription className="leading-relaxed">
              가입한 이메일 주소를 입력해주세요.<br />임시 비밀번호를 메일로 보내드려요.
            </DialogDescription>
          )}
        </div>
        {sent ? (
          <div className="mt-6 flex flex-col gap-6">
            <div role="status" className="rounded-input bg-primary-bg p-4 text-sm leading-relaxed text-foreground">
              <p className="font-bold">임시 비밀번호 발송을 요청했어요.</p>
              <p className="mt-2">임시 비밀번호로 로그인후 마이페이지에서 비밀번호 변경을 해주세요.</p>
            </div>
            <Button type="button" onClick={close}>로그인으로 돌아가기</Button>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-6" aria-busy={sending}>
            <Input
              label="이메일 주소"
              type="text"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="example@email.com"
              pattern={EMAIL_INPUT_PATTERN}
              maxLength={EMAIL_MAX_LENGTH}
              value={email}
              onChange={event => {
                setEmail(sanitizeEmailInput(event.currentTarget.value));
                setError(null);
              }}
              disabled={sending}
              required
            />
            {error && <p role="alert" className="text-sm text-danger-strong">{error}</p>}
            <Button type="submit" disabled={sending || !email.trim()}>
              {sending ? '발송 요청 중...' : '임시비밀번호 발송'}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
