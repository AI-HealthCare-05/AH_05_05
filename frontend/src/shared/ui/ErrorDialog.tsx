import { Button } from './Button';
import { Card } from './Card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './dialog';

/**
 * 작업 실패 팝업.
 *
 * **진입 실패에는 쓰지 마세요.** 팝업은 뒤에 남아 있는 화면이 있어야 의미가 있습니다.
 * 진입 로드가 실패한 화면은 뒤에 아무것도 없어서 팝업을 닫으면 빈 화면만 남습니다 —
 * 그 경우는 화면 안 카드(`loadError` → `Card`)가 맞는 형태입니다.
 * 여기 쓰는 건 사용자가 버튼을 눌러서 생긴 실패입니다(업로드·저장 등).
 *
 * `showCloseButton={false}` 로 두어 실패를 무시하고 지나가지 못하게 합니다.
 * 실패를 라우트로 두지 않는 이유는 브라우저 뒤로가기와 싸우게 되기 때문입니다 —
 * 실패는 화면이 아니라 상태입니다.
 *
 * `O08 LowConfidenceConfirmDialog` 와 같은 Dialog 구성입니다.
 */
export interface ErrorDialogProps {
  open: boolean;
  title: string;
  /** 서버가 준 문구를 그대로 넣으세요. 여기서 새 문구를 만들지 마세요. */
  message: string;
  /** 재시도 버튼 라벨. 기본 "다시 시도" */
  retryLabel?: string;
  onRetry: () => void;
  /** 두 번째 버튼. 없으면 렌더하지 않습니다 */
  secondaryLabel?: string;
  onSecondary?: () => void;
}

export function ErrorDialog({
  open,
  title,
  message,
  retryLabel = '다시 시도',
  onRetry,
  secondaryLabel,
  onSecondary,
}: ErrorDialogProps) {
  return (
    // 실패를 무시하고 닫을 수 없어야 하므로 ESC·오버레이 클릭으로도 닫지 않습니다.
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent showCloseButton={false} className="bg-warning-bg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <Card tone="warning">
          {/* message 는 ApiError.message — shared/api/client.ts 가 서버 문구 또는
              FALLBACK_MESSAGE 를 이미 채워줍니다. 여기서 만들면 문구가 두 벌이 됩니다. */}
          <DialogDescription>{message}</DialogDescription>
        </Card>

        <DialogFooter>
          <Button onClick={onRetry}>{retryLabel}</Button>
          {secondaryLabel && onSecondary && (
            <Button variant="secondary" onClick={onSecondary}>
              {secondaryLabel}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
