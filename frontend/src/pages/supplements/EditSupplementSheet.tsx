import { useEffect, useId, useState } from 'react';
import { Star } from 'lucide-react';
import type { Supplement, UpdateSupplementPayload } from '@/entities/supplement';
import type { MealSlot } from '@/shared/model/mealSlot';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DoseSlotFields,
  StatusBadge,
} from '@/shared/ui';

interface EditSupplementSheetProps {
  open: boolean;
  supplement: Supplement | null;
  maskedName: string;
  onOpenChange: (open: boolean) => void;
  onSave: (supplementId: number, payload: UpdateSupplementPayload) => Promise<void>;
  onStop: (supplementId: number) => Promise<void>;
}

export function EditSupplementSheet({
  open,
  supplement,
  maskedName,
  onOpenChange,
  onSave,
  onStop,
}: EditSupplementSheetProps) {
  const noteId = useId();
  const reviewId = useId();
  const [doseAmount, setDoseAmount] = useState(1);
  const [doseStep, setDoseStep] = useState(1);
  const [slots, setSlots] = useState<MealSlot[]>(['morning']);
  const [score, setScore] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [reviewBody, setReviewBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [confirmStopOpen, setConfirmStopOpen] = useState(false);

  useEffect(() => {
    if (!open || !supplement) return;
    setDoseAmount(supplement.doseAmount);
    setDoseStep(doseStepFor(supplement.doseAmount));
    setSlots([...supplement.slots]);
    setScore(supplement.score);
    setNote(supplement.note ?? '');
    setReviewBody(supplement.reviewBody ?? '');
    setSaving(false);
    setStopping(false);
    setConfirmStopOpen(false);
  }, [open, supplement]);

  async function save() {
    if (!supplement || slots.length === 0 || saving) return;
    setSaving(true);
    try {
      await onSave(supplement.supplementId, {
        doseAmount,
        slots,
        score,
        note: note.trim() || null,
        reviewBody: reviewBody.trim() || null,
      });
      onOpenChange(false);
    } catch {
      // 저장 실패는 부모 화면의 ErrorDialog가 표시합니다.
    } finally {
      setSaving(false);
    }
  }

  async function stop() {
    if (!supplement || stopping) return;
    setStopping(true);
    try {
      await onStop(supplement.supplementId);
      setConfirmStopOpen(false);
      onOpenChange(false);
    } catch {
      // 저장 실패는 부모 화면의 ErrorDialog가 표시합니다.
    } finally {
      setStopping(false);
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent variant="sheet" aria-describedby="supplement-edit-description">
          <div className="pr-10">
            <DialogTitle className="text-xl">{supplement?.name ?? '영양제'}</DialogTitle>
            <DialogDescription id="supplement-edit-description" className="sr-only">
              1회 섭취량, 복용 시간, 별점과 메모, 후기를 수정합니다.
            </DialogDescription>
            {supplement && !supplement.nutrientDataAvailable && (
              <StatusBadge type="done" className="mt-2 px-2.5 py-1 text-sm">
                성분 정보 없음
              </StatusBadge>
            )}
          </div>

          <DoseSlotFields
            doseAmount={doseAmount}
            doseUnit={supplement?.doseUnit ?? '정'}
            doseStep={doseStep}
            slots={slots}
            onDoseAmountChange={setDoseAmount}
            onSlotsChange={setSlots}
          />

          <div
            role="group"
            aria-labelledby="supplement-score-label"
            className="flex flex-col gap-1.5"
          >
            <p id="supplement-score-label" className="text-sm font-bold text-foreground">
              먹어보니 어때요?
            </p>
            <div className="flex items-center gap-1">
              {Array.from({ length: 5 }, (_, index) => index + 1).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-label={`별 ${value}점`}
                  aria-pressed={score === value}
                  className="flex size-touch items-center justify-center rounded-input text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => setScore((current) => (current === value ? null : value))}
                >
                  <Star
                    aria-hidden
                    className={`size-7 ${score !== null && value <= score ? 'fill-current' : ''}`}
                  />
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor={noteId} className="text-sm font-bold text-foreground">
              메모{' '}
              <span className="text-xs font-normal text-muted-foreground">나만 볼 수 있어요</span>
            </label>
            <textarea
              id={noteId}
              value={note}
              maxLength={500}
              rows={3}
              placeholder="복용하면서 기억할 점"
              className="w-full resize-none rounded-input border border-input bg-card px-3.5 py-3 text-base text-foreground placeholder:text-disabled-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor={reviewId} className="text-sm font-bold text-foreground">
              후기{' '}
              <span className="text-xs font-normal text-muted-foreground">
                {maskedName} 으로 다른 사람에게 보여요
              </span>
            </label>
            <textarea
              id={reviewId}
              value={reviewBody}
              maxLength={500}
              rows={3}
              placeholder="먹어본 경험을 남겨주세요"
              className="w-full resize-none rounded-input border border-input bg-card px-3.5 py-3 text-base text-foreground placeholder:text-disabled-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              onChange={(event) => setReviewBody(event.target.value)}
            />
          </div>

          <Button disabled={slots.length === 0 || saving} onClick={() => void save()}>
            {saving ? '저장 중...' : '저장'}
          </Button>
          <button
            type="button"
            className="min-h-touch text-sm font-bold text-danger-strong"
            onClick={() => setConfirmStopOpen(true)}
          >
            복용 중단하기
          </button>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmStopOpen} onOpenChange={setConfirmStopOpen}>
        <DialogContent showCloseButton={false} aria-describedby="supplement-stop-description">
          <DialogHeader>
            <DialogTitle>{supplement?.name ?? '영양제'} 복용을 중단할까요?</DialogTitle>
            <DialogDescription id="supplement-stop-description">
              성분 합계에서 제외됩니다. 다시 추가할 수 있어요.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" disabled={stopping} onClick={() => setConfirmStopOpen(false)}>
              취소
            </Button>
            <Button variant="danger" disabled={stopping} onClick={() => void stop()}>
              {stopping ? '중단 중...' : '중단하기'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function doseStepFor(amount: number): number {
  if (!Number.isFinite(amount)) return 1;
  const fraction = Math.round((amount % 1) * 1_000) / 1_000;
  return fraction > 0 ? fraction : 1;
}
