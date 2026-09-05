import { useEffect, useRef, useState } from 'react';
import { XIcon } from 'lucide-react';
import { listCommonCodes, type CommonCodeItem } from '@/entities/common-code';
import {
  saveChatFeedback,
  type ChatFeedbackPayload,
  type ChatFeedbackResult,
} from '@/entities/chat';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/shared/ui';
import { cn } from '@/shared/lib/cn';

type FeedbackStep = 'end' | 'positive' | 'negative';
type CommonCodeLoader = (category: string, groupCode: string) => Promise<CommonCodeItem[]>;
type FeedbackSaver = (
  sessionId: number,
  payload: ChatFeedbackPayload,
) => Promise<ChatFeedbackResult>;

const FEEDBACK_SAVE_ERROR = '평가를 저장하지 못했어요. 다시 시도해주세요.';

interface ChatFeedbackSheetProps {
  open: boolean;
  sessionId?: number | null;
  onOpenChange: (open: boolean) => void;
  onFinish: () => void;
  reasonLoader?: CommonCodeLoader;
  feedbackSaver?: FeedbackSaver;
}

export function ChatFeedbackSheet({
  open,
  sessionId = null,
  onOpenChange,
  onFinish,
  reasonLoader = listCommonCodes,
  feedbackSaver = saveChatFeedback,
}: ChatFeedbackSheetProps) {
  const [step, setStep] = useState<FeedbackStep>('end');
  const [reasons, setReasons] = useState<CommonCodeItem[]>([]);
  const [selectedReason, setSelectedReason] = useState<string | null>(null);
  const [reasonsLoading, setReasonsLoading] = useState(false);
  const [reasonsError, setReasonsError] = useState<string | null>(null);
  const [reasonsRetryKey, setReasonsRetryKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveGenerationRef = useRef(0);

  useEffect(() => {
    if (!open || step === 'end') return;

    let cancelled = false;
    const groupCode = step === 'positive' ? 'P_REASON' : 'N_REASON';
    setReasons([]);
    setSelectedReason(null);
    setReasonsLoading(true);
    setReasonsError(null);

    void reasonLoader('CHAT', groupCode)
      .then((items) => {
        if (cancelled) return;
        setReasons(items);
      })
      .catch(() => {
        if (cancelled) return;
        setReasonsError('사유를 불러오지 못했어요');
      })
      .finally(() => {
        if (!cancelled) setReasonsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, reasonLoader, reasonsRetryKey, step]);

  useEffect(() => {
    if (!open) {
      saveGenerationRef.current += 1;
      setStep('end');
      setReasons([]);
      setSelectedReason(null);
      setReasonsLoading(false);
      setReasonsError(null);
      setReasonsRetryKey(0);
      setSaving(false);
      setSaveError(null);
    }
  }, [open]);

  function chooseStep(nextStep: Exclude<FeedbackStep, 'end'>) {
    saveGenerationRef.current += 1;
    setStep(nextStep);
    setSelectedReason(null);
    setReasonsError(null);
    setSaveError(null);
  }

  function closeSheet() {
    saveGenerationRef.current += 1;
    onOpenChange(false);
  }

  function skip() {
    closeSheet();
    onFinish();
  }

  function chooseReason(reasonCode: string) {
    setSelectedReason((current) => (current === reasonCode ? null : reasonCode));
    setSaveError(null);
  }

  async function submit() {
    if (step === 'end' || saving) return;
    if (sessionId === null) {
      setSaveError(FEEDBACK_SAVE_ERROR);
      return;
    }

    const saveGeneration = saveGenerationRef.current + 1;
    saveGenerationRef.current = saveGeneration;
    setSaving(true);
    setSaveError(null);
    try {
      await feedbackSaver(sessionId, {
        isLike: step === 'positive',
        reasonCode: selectedReason,
      });
      if (saveGenerationRef.current !== saveGeneration) return;
      closeSheet();
      onFinish();
    } catch {
      if (saveGenerationRef.current !== saveGeneration) return;
      setSaveError(FEEDBACK_SAVE_ERROR);
    } finally {
      if (saveGenerationRef.current === saveGeneration) setSaving(false);
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) saveGenerationRef.current += 1;
    onOpenChange(nextOpen);
  }

  const title = step === 'end' ? '상담 종료' : '상담 평가';
  const positive = step === 'positive';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        variant="sheet"
        className="max-h-[100dvh] overflow-hidden"
      >
        <DialogTitle className="pr-10 text-xl">{title}</DialogTitle>
        <button
          type="button"
          aria-label="평가 닫기"
          onClick={closeSheet}
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
            <Button variant="secondary" onClick={skip}>
              건너뛰고 종료
            </Button>
          </>
        ) : (
          <>
            <DialogDescription className="text-base font-bold text-foreground">
              {positive ? '좋았던 점을 선택해주세요' : '아쉬웠던 점을 선택해주세요'}
            </DialogDescription>

            {reasonsLoading && (
              <p role="status" className="text-sm text-muted-foreground">
                사유를 불러오는 중이에요
              </p>
            )}

            {reasonsError !== null && (
              <div className="flex flex-col gap-2">
                <p role="alert" className="text-sm text-danger-strong">
                  {reasonsError}
                </p>
                <Button
                  variant="secondary"
                  onClick={() => setReasonsRetryKey((current) => current + 1)}
                  disabled={reasonsLoading}
                >
                  다시 시도
                </Button>
              </div>
            )}

            {!reasonsLoading && reasonsError === null && reasons.length > 0 && (
              <div
                role="region"
                aria-label="평가 사유"
                className="min-h-0 w-full overflow-y-auto overscroll-contain"
                style={{ maxHeight: 'calc(100dvh - 220px)' }}
              >
                <div className="mx-auto flex w-full max-w-[310px] flex-col gap-1.5">
                  {reasons.map((reason) => {
                    const selected = reason.detailCode === selectedReason;
                    return (
                      <button
                        key={reason.detailCode}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => chooseReason(reason.detailCode)}
                        className={cn(
                          'min-h-touch w-full rounded-input border px-4 text-left text-caption font-medium',
                          positive
                            ? selected
                              ? 'border-[1.5px] border-primary bg-action-soft font-bold text-primary'
                              : 'border-border bg-card text-muted-foreground hover:bg-muted-bg'
                            : selected
                              ? 'border-[1.5px] border-danger bg-danger-bg font-bold text-danger'
                              : 'border-border bg-card text-muted-foreground hover:bg-muted-bg',
                        )}
                      >
                        {reason.detailName}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {saveError !== null && (
              <p role="alert" className="text-sm text-danger-strong">
                {saveError}
              </p>
            )}

            <div className="sticky bottom-0 bg-card pt-1">
              <Button
                variant={positive ? 'primary' : 'danger'}
                disabled={saving}
                onClick={() => void submit()}
              >
                제출하고 종료
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
