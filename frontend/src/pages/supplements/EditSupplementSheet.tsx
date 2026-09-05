import { useEffect, useId, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import type { Supplement, UpdateSupplementPayload } from '@/entities/supplement';
import { mealSlotLabel, type MealSlot } from '@/shared/model/mealSlot';
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
  onProductInfo?: (productId: string) => void;
}

export function EditSupplementSheet({
  open,
  supplement,
  maskedName,
  onOpenChange,
  onSave,
  onStop,
  onProductInfo,
}: EditSupplementSheetProps) {
  const [doseAmount, setDoseAmount] = useState(1);
  const [doseStep, setDoseStep] = useState(1);
  const [slots, setSlots] = useState<MealSlot[]>(['morning']);
  const [score, setScore] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [reviewBody, setReviewBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [confirmStopOpen, setConfirmStopOpen] = useState(false);
  const [ratingEditOpen, setRatingEditOpen] = useState(false);
  const [ratingDraft, setRatingDraft] = useState<number | null>(null);
  const [ratingSaving, setRatingSaving] = useState(false);
  const [recordEditTarget, setRecordEditTarget] = useState<'note' | 'review' | null>(null);

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
    setRatingEditOpen(false);
    setRatingDraft(supplement.score);
    setRatingSaving(false);
    setRecordEditTarget(null);
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

  async function saveRating() {
    if (!supplement || ratingSaving || slots.length === 0) return;
    setRatingSaving(true);
    try {
      await onSave(supplement.supplementId, {
        doseAmount: supplement.doseAmount,
        slots: supplement.slots,
        score: ratingDraft,
        note: note.trim() || null,
        reviewBody: reviewBody.trim() || null,
      });
      setScore(ratingDraft);
      setRatingEditOpen(false);
    } catch {
      // 저장 실패는 부모 화면의 ErrorDialog가 표시합니다.
    } finally {
      setRatingSaving(false);
    }
  }

  async function saveRecord(target: 'note' | 'review', value: string) {
    if (!supplement) return;
    const nextNote = target === 'note' ? value : note;
    const nextReview = target === 'review' ? value : reviewBody;
    await onSave(supplement.supplementId, {
      // Record editing must not silently save unsubmitted dose/slot edits underneath it.
      doseAmount: supplement.doseAmount,
      slots: supplement.slots,
      score,
      note: nextNote || null,
      reviewBody: nextReview || null,
    });
    setNote(nextNote);
    setReviewBody(nextReview);
    setRecordEditTarget(null);
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          variant="sheet"
          aria-label={supplement?.name ?? '영양제'}
          aria-describedby="supplement-edit-description"
          className="max-h-[92dvh] overflow-y-auto pb-6"
        >
          <div className="pr-10">
            <DialogTitle className="sr-only">{supplement?.name ?? '영양제'}</DialogTitle>
            <h1 className="text-2xl font-bold text-foreground">내 영양제</h1>
            <DialogDescription id="supplement-edit-description" className="sr-only">
              1회 섭취량, 복용 시간, 별점과 메모, 후기를 수정합니다.
            </DialogDescription>
          </div>

          {supplement && (
            <>
              <section
                aria-label="내 영양제 요약"
                className="rounded-card border border-border bg-card p-4 shadow-card"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-xl font-bold text-foreground">{supplement.name}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {formatDose(supplement.doseAmount, supplement.doseUnit)} ·{' '}
                      {supplement.slots.map((slot) => mealSlotLabel(slot, 'short')).join(' · ')}
                      {note.trim() ? ' · 메모 있음' : ''}
                    </p>
                  </div>
                  {score !== null && (
                    <span
                      aria-label={`별 ${score}점`}
                      className="shrink-0 text-lg font-bold text-warning-strong"
                    >
                      {displayStars(score)}
                    </span>
                  )}
                </div>
              </section>

              <section className="flex flex-col gap-3" aria-labelledby="my-supplement-record-title">
                <h2 id="my-supplement-record-title" className="text-xl font-bold text-foreground">
                  내 기록
                </h2>
                <div className="rounded-card border border-border bg-card p-4 shadow-card">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-base font-bold text-foreground">내 별점</h3>
                    <button
                      type="button"
                      className="flex min-h-touch items-center justify-center px-1 text-sm font-bold text-primary-strong"
                      onClick={() => {
                        setRatingDraft(score);
                        setRatingEditOpen(true);
                      }}
                    >
                      별점 수정
                    </button>
                  </div>
                  <p
                    aria-label={`별 ${score ?? 0}점`}
                    className="mt-1 text-2xl font-bold text-warning-strong"
                  >
                    {displayStars(score)}
                  </p>
                </div>
                <div role="group" aria-label="내 메모" className="rounded-card border border-border bg-card p-4 shadow-card">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-base font-bold text-foreground">내 메모</h3>
                    <button type="button" className="min-h-touch px-1 text-sm font-bold text-primary-strong" onClick={() => setRecordEditTarget('note')}>
                      {note.trim() ? '수정하기' : '등록하기'}
                    </button>
                  </div>
                  <p className="mt-4 whitespace-pre-wrap break-words text-sm text-foreground">
                    {note.trim() || '작성한 메모가 없어요.'}
                  </p>
                </div>
                <div role="group" aria-label="내 후기" className="rounded-card border border-border bg-card p-4 shadow-card">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-base font-bold text-foreground">내 후기</h3>
                    <button type="button" className="min-h-touch px-1 text-sm font-bold text-primary-strong" onClick={() => setRecordEditTarget('review')}>
                      {reviewBody.trim() ? '수정하기' : '등록하기'}
                    </button>
                  </div>
                  <p className="mt-4 whitespace-pre-wrap break-words text-sm text-foreground">
                    {reviewBody.trim() || '작성한 후기가 없어요.'}
                  </p>
                </div>
                {supplement.productId && onProductInfo && (
                  <button
                    type="button"
                    className="flex min-h-touch items-center justify-between rounded-control border border-border bg-card px-4 text-left text-sm font-bold text-primary-strong shadow-card"
                    onClick={() => onProductInfo(supplement.productId!)}
                  >
                    <span>제품 정보 보기</span>
                    <ChevronRight aria-hidden className="size-5 text-muted-foreground" />
                  </button>
                )}
              </section>

              <div className="border-t border-border pt-4">
                <h2 className="mb-3 text-lg font-bold text-foreground">복용 정보 수정</h2>
              </div>
            </>
          )}

          {supplement && !supplement.nutrientDataAvailable && (
            <StatusBadge type="done" className="px-2.5 py-1 text-sm">
              성분 정보 없음
            </StatusBadge>
          )}

          <DoseSlotFields
            doseAmount={doseAmount}
            doseUnit={supplement?.doseUnit ?? '정'}
            doseStep={doseStep}
            slots={slots}
            onDoseAmountChange={setDoseAmount}
            onSlotsChange={setSlots}
          />

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

      {open && recordEditTarget !== null && (
        <SupplementRecordEditor
          key={recordEditTarget} target={recordEditTarget}
          value={recordEditTarget === 'note' ? note : reviewBody} maskedName={maskedName}
          onClose={() => setRecordEditTarget(null)} onSave={value => saveRecord(recordEditTarget, value)}
        />
      )}

      <Dialog
        open={ratingEditOpen}
        onOpenChange={(nextOpen) => {
          setRatingEditOpen(nextOpen);
          if (!nextOpen) setRatingDraft(score);
        }}
      >
        <DialogContent
          variant="sheet"
          aria-describedby="supplement-rating-description"
          className="gap-5 pb-6"
        >
          <DialogTitle className="text-2xl">별점 수정</DialogTitle>
          <DialogDescription id="supplement-rating-description">
            {supplement?.name ?? '영양제'}는 어떠셨나요?
          </DialogDescription>
          <div role="group" aria-label="별점 선택" className="flex items-center justify-between">
            {Array.from({ length: 5 }, (_, index) => index + 1).map((value) => (
              <button
                key={value}
                type="button"
                aria-label={`별 ${value}점`}
                aria-pressed={ratingDraft === value}
                className={`flex size-touch items-center justify-center rounded-input focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  ratingDraft !== null && value <= ratingDraft
                    ? 'text-warning-strong'
                    : 'text-muted-foreground'
                }`}
                onClick={() => setRatingDraft(value)}
              >
                <span aria-hidden className="text-[34px] leading-none">
                  {ratingDraft !== null && value <= ratingDraft ? '★' : '☆'}
                </span>
              </button>
            ))}
          </div>
          <p className="text-sm font-bold text-primary-strong">
            {ratingDraft === null ? '별점을 선택해주세요' : `${ratingDraft}점 · ${ratingDescription(ratingDraft)}`}
          </p>
          <Button disabled={ratingSaving} onClick={() => void saveRating()}>
            {ratingSaving ? '저장 중...' : '저장'}
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmStopOpen} onOpenChange={setConfirmStopOpen}>
        <DialogContent
          showCloseButton={false}
          aria-describedby="supplement-stop-description"
          className="gap-4 p-6"
        >
          <DialogHeader>
            <DialogTitle>{supplement?.name ?? '영양제'} 복용을 중단할까요?</DialogTitle>
            <DialogDescription id="supplement-stop-description">
              성분 합계에서 제외됩니다. 다시 추가할 수 있어요.
            </DialogDescription>
          </DialogHeader>
          {supplement && (
            <p className="rounded-control bg-danger-bg px-3 py-3 text-center text-sm font-bold text-danger-strong">
              {supplement.name} · {formatDose(doseAmount, supplement.doseUnit)} ·{' '}
              {slots.map((slot) => mealSlotLabel(slot, 'short')).join(' · ')}
            </p>
          )}
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

function formatDose(amount: number, unit: string): string {
  return `${new Intl.NumberFormat('ko-KR').format(amount)}${unit}`;
}

function SupplementRecordEditor({ target, value, maskedName, onSave, onClose }: {
  target: 'note' | 'review';
  value: string;
  maskedName: string;
  onSave: (value: string) => Promise<void>;
  onClose: () => void;
}) {
  const fieldId = useId();
  const descriptionId = useId();
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const label = target === 'note' ? '메모' : '후기';

  async function save() {
    if (saving) return;
    setSaving(true);
    try {
      await onSave(draft.trim());
    } catch {
      // The parent's error dialog explains the failure; keep this editor and its draft.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(nextOpen) => { if (!nextOpen && !saving) onClose(); }}>
      <DialogContent variant="sheet" aria-describedby={descriptionId} className="max-h-[92dvh] overflow-y-auto pb-6">
        <DialogTitle className="text-2xl">{label} 편집</DialogTitle>
        <DialogDescription id={descriptionId}>{label}를 편집한 뒤 저장해주세요.</DialogDescription>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={fieldId} className="text-sm font-bold text-foreground">
            {label}{' '}
            <span className="text-xs font-normal text-muted-foreground">
              {target === 'note' ? '나만 볼 수 있어요' : `${maskedName} 으로 다른 사람에게 보여요`}
            </span>
          </label>
          <textarea
            id={fieldId} value={draft} maxLength={500} rows={3} disabled={saving}
            placeholder={target === 'note' ? '복용하면서 기억할 점' : '먹어본 경험을 남겨주세요'}
            className="w-full resize-none rounded-input border border-input bg-card px-3.5 py-3 text-base text-foreground placeholder:text-disabled-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            onChange={event => setDraft(event.target.value)}
          />
        </div>
        <Button disabled={saving} onClick={() => void save()}>{saving ? '저장 중...' : '저장'}</Button>
      </DialogContent>
    </Dialog>
  );
}

function displayStars(score: number | null): string {
  const filled = Math.max(0, Math.min(5, Math.round(score ?? 0)));
  return `${'★'.repeat(filled)}${'☆'.repeat(5 - filled)}`;
}

function ratingDescription(score: number): string {
  if (score >= 5) return '아주 좋아요';
  if (score >= 4) return '좋아요';
  if (score >= 3) return '보통이에요';
  if (score >= 2) return '아쉬워요';
  return '별로예요';
}

function doseStepFor(amount: number): number {
  if (!Number.isFinite(amount)) return 1;
  const fraction = Math.round((amount % 1) * 1_000) / 1_000;
  return fraction > 0 ? fraction : 1;
}
