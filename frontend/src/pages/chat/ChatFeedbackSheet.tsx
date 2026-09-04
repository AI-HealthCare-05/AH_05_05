import { useEffect, useState } from 'react';
import { XIcon } from 'lucide-react';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/shared/ui';
import { cn } from '@/shared/lib/cn';

type FeedbackStep = 'end' | 'positive' | 'negative';

const REASONS = {
  positive: ['이해하기 쉬워요', '도움이 됐어요', '안심됐어요'],
  negative: ['답변이 어려워요', '도움이 부족해요', '내용이 길어요'],
} as const;

interface ChatFeedbackSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** API가 생기기 전까지는 평가를 화면 상태로만 처리하고 상담을 닫습니다. */
export function ChatFeedbackSheet({ open, onOpenChange }: ChatFeedbackSheetProps) {
  const [step, setStep] = useState<FeedbackStep>('end');
  const [selectedReason, setSelectedReason] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep('end');
    setSelectedReason(null);
  }, [open]);

  function chooseStep(nextStep: Exclude<FeedbackStep, 'end'>) {
    setStep(nextStep);
    setSelectedReason(REASONS[nextStep][0]);
  }

  function finish() {
    onOpenChange(false);
  }

  const title = step === 'end' ? '상담 종료' : '상담 평가';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="w-[calc(100%-2.5rem)] max-w-[350px] rounded-sheet p-5"
      >
        <DialogTitle className="pr-10 text-xl">
          {title}
        </DialogTitle>
        <button
          type="button"
          aria-label="평가 닫기"
          onClick={() => onOpenChange(false)}
          className="absolute right-3 top-3 flex size-touch items-center justify-center rounded-input text-muted-foreground hover:bg-muted-bg"
        >
          <XIcon aria-hidden className="size-6" />
        </button>

        {step === 'end' ? (
          <>
            <DialogDescription className="text-base font-bold text-foreground">
              이번 상담은 어떠셨나요?
            </DialogDescription>
            <div className="grid grid-cols-2 gap-3.5">
              <button
                type="button"
                onClick={() => chooseStep('positive')}
                className="min-h-[88px] rounded-card border border-border bg-card text-base font-bold text-primary hover:bg-primary-bg"
              >
                좋아요
              </button>
              <button
                type="button"
                onClick={() => chooseStep('negative')}
                className="min-h-[88px] rounded-card border border-border bg-card text-base font-bold text-danger hover:bg-danger-bg"
              >
                아쉬워요
              </button>
            </div>
            <p className="text-center text-unit text-muted-foreground">
              선택하면 간단한 이유를 남길 수 있어요.
            </p>
            <Button variant="secondary" onClick={finish}>
              건너뛰고 종료
            </Button>
          </>
        ) : (
          <>
            <DialogDescription className="text-base font-bold text-foreground">
              {step === 'positive' ? '좋았던 점을 선택해주세요' : '아쉬웠던 점을 선택해주세요'}
            </DialogDescription>
            <div className="flex flex-col gap-1.5">
              {REASONS[step].map((reason) => {
                const selected = reason === selectedReason;
                return (
                  <button
                    key={reason}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setSelectedReason(reason)}
                    className={cn(
                      'min-h-touch rounded-input border px-3 text-left text-caption',
                      step === 'positive'
                        ? selected
                          ? 'border-primary bg-primary-bg font-bold text-primary'
                          : 'border-border bg-card text-muted-foreground hover:bg-muted-bg'
                        : selected
                          ? 'border-danger bg-danger-bg font-bold text-danger'
                          : 'border-border bg-card text-muted-foreground hover:bg-muted-bg',
                    )}
                  >
                    {reason}
                  </button>
                );
              })}
            </div>
            <Button
              variant={step === 'positive' ? 'primary' : 'danger'}
              disabled={selectedReason === null}
              onClick={finish}
            >
              제출하고 종료
            </Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
