import { Check } from 'lucide-react';
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle } from '@/shared/ui';

interface LoginPromptSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onLogin: () => void;
}

const BENEFITS = [
  '약봉투를 등록하고 복약 알림 받기',
  '영양제 성분 합계와 복약 표준 가이드',
  '내 약을 근거로 답하는 챗봇',
] as const;

export function LoginPromptSheet({ open, onOpenChange, onLogin }: LoginPromptSheetProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" showCloseButton={false} aria-describedby="login-prompt-copy">
        <div aria-hidden className="mx-auto h-1 w-10 rounded-pill bg-border" />
        <div className="flex flex-col gap-2 pt-2">
          <DialogTitle className="text-xl">로그인하고, 나만의 복약관리를 시작해 보세요.</DialogTitle>
        </div>

        <ul className="flex flex-col gap-3" aria-label="로그인 후 이용할 수 있는 기능">
          {BENEFITS.map((benefit) => (
            <li key={benefit} className="flex items-center gap-3 text-base text-foreground">
              <span className="flex size-touch shrink-0 items-center justify-center rounded-pill bg-primary-bg text-primary-strong">
                <Check aria-hidden className="size-5" />
              </span>
              {benefit}
            </li>
          ))}
        </ul>

        <div className="flex flex-col gap-2">
          <Button onClick={onLogin}>로그인 · 회원가입</Button>
          <button
            type="button"
            className="min-h-touch text-sm font-bold text-muted-foreground"
            onClick={() => onOpenChange(false)}
          >
            다음에 할게요
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
