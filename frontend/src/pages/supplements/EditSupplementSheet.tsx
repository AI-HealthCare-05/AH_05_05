import { useEffect, useState } from 'react';
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
  onOpenChange: (open: boolean) => void;
  onSave: (supplementId: number, payload: UpdateSupplementPayload) => Promise<void>;
  onStop: (supplementId: number) => Promise<void>;
}

export function EditSupplementSheet({
  open,
  supplement,
  onOpenChange,
  onSave,
  onStop,
}: EditSupplementSheetProps) {
  const [dailyCount, setDailyCount] = useState(1);
  const [slots, setSlots] = useState<MealSlot[]>(['morning']);
  const [saving, setSaving] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [confirmStopOpen, setConfirmStopOpen] = useState(false);

  useEffect(() => {
    if (!open || !supplement) return;
    setDailyCount(supplement.dailyCount);
    setSlots([...supplement.slots]);
    setSaving(false);
    setStopping(false);
    setConfirmStopOpen(false);
  }, [open, supplement]);

  async function save() {
    if (!supplement || slots.length === 0 || saving) return;
    setSaving(true);
    try {
      await onSave(supplement.supplementId, { dailyCount, slots });
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
              하루 섭취 정수와 복용 시간을 수정합니다.
            </DialogDescription>
            {supplement && !supplement.nutrientDataAvailable && (
              <StatusBadge type="done" className="mt-2 px-2.5 py-1 text-sm">
                성분 정보 없음
              </StatusBadge>
            )}
          </div>

          <DoseSlotFields
            dailyCount={dailyCount}
            slots={slots}
            onDailyCountChange={setDailyCount}
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
