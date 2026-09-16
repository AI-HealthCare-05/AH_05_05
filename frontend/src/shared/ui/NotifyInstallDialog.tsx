import type { ReactNode } from 'react';
import { HousePlus, Share } from 'lucide-react';
import { Button } from './Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './dialog';

export interface NotifyInstallDialogProps {
  open: boolean;
  onConfirm: () => void;
}

/**
 * iOS/iPadOS 일반 탭에서만 보여주는 홈 화면 웹 앱 실행 안내입니다.
 * 실제 브라우저 메뉴를 조작할 수 없으므로, 공유 버튼과 웹 앱 토글을
 * 작은 HTML 안내 카드로 명확하게 재현합니다.
 */
export function NotifyInstallDialog({ open, onConfirm }: NotifyInstallDialogProps) {
  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent showCloseButton={false} className="gap-3">
        <DialogHeader>
          <DialogTitle>홈 화면에서 RxVita를 열어주세요</DialogTitle>
          <DialogDescription>알림을 켜려면 브라우저에서 다음 순서로 실행해주세요.</DialogDescription>
        </DialogHeader>

        <ol aria-label="홈 화면 웹 앱 실행 순서" className="flex flex-col gap-2">
          <InstallStep
            number="1"
            icon={<Share className="size-5" strokeWidth={2.5} aria-hidden="true" />}
            label="브라우저 공유 버튼"
          />
          <InstallStep
            number="2"
            icon={<HousePlus className="size-5" strokeWidth={2.5} aria-hidden="true" />}
            label="홈 화면에 추가"
          />
          <InstallStep
            number="3"
            icon={<IosWebAppToggle />}
            label="‘웹 앱으로 열기’ 켜기"
          />
          <InstallStep
            number="4"
            icon={
              <img
                src="/icons/icon-192.png"
                alt=""
                aria-hidden="true"
                className="size-9 rounded-[10px] object-cover"
              />
            }
            label="RxVita 아이콘 실행"
          />
        </ol>

        <DialogFooter>
          <Button onClick={onConfirm}>확인</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InstallStep({ number, icon, label }: { number: string; icon: ReactNode; label: string }) {
  return (
    <li className="flex min-h-12 items-center gap-3 rounded-input border border-border bg-background px-3 py-1.5">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-pill bg-primary text-xs font-bold text-card">
        {number}
      </span>
      <span
        aria-hidden="true"
        className="flex size-9 shrink-0 items-center justify-center rounded-input bg-primary-bg text-primary-strong"
      >
        {icon}
      </span>
      <span className="text-sm font-bold text-foreground">{label}</span>
    </li>
  );
}

function IosWebAppToggle() {
  return (
    <span className="relative block h-6 w-11 rounded-pill bg-primary" aria-hidden="true">
      <span className="absolute right-0.5 top-0.5 size-5 rounded-pill bg-card shadow-sm" />
    </span>
  );
}
