import { useEffect, useState } from 'react';
import type { OcrMedication } from '@/entities/document';
import { cn } from '@/shared/lib/cn';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui';

/**
 * 결과 확인 목록에서 누른 약 하나만 수정하는 시트입니다.
 *
 * 결과 확인 화면이 이미 전체 약 목록이므로 여기서 같은 목록을 반복하지 않습니다.
 * 시트의 저장은 부모 화면 상태에만 반영되고, 서버 저장은 결과 확인 화면의
 * [저장하고 복약 시간 설정]에서 일어납니다. 이 두 단계보다 저장 버튼을 더 늘리지 마세요.
 *
 * frequencyText의 "필요 시" 접두어 가드는 목록 시절의 표시 전용 로직이어서 제거됐지만,
 * OCR note 원문 자체는 draft에 보존합니다. 필요 시 약을 저장할 때 note가 사라지면 이후
 * 복약 시간 화면이 PRN 안내를 만들 근거를 잃습니다.
 */

export interface MedicationEditDialogProps {
  open: boolean;
  medication: OcrMedication | null;
  mode: 'add' | 'edit';
  onOpenChange: (open: boolean) => void;
  onSave: (medication: OcrMedication) => void;
  onDelete?: () => void;
}

interface Draft {
  name: string;
  dose: string;
  timesPerDay: number | null;
  days: number | null;
  note: string;
}

const TIMES_PER_DAY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '1', label: '1회' },
  { value: '2', label: '2회' },
  { value: '3', label: '3회' },
  { value: '4', label: '4회' },
  { value: 'prn', label: '필요 시' },
];

const EMPTY_DRAFT: Draft = {
  name: '',
  dose: '',
  timesPerDay: 1,
  days: 1,
  note: '',
};

function toDraft(medication: OcrMedication | null): Draft {
  if (!medication) return EMPTY_DRAFT;
  return {
    name: medication.name,
    dose: medication.dose,
    timesPerDay: medication.timesPerDay,
    days: medication.days,
    note: medication.note,
  };
}

function timesPerDayToSelectValue(timesPerDay: number | null): string {
  return timesPerDay === null ? 'prn' : String(timesPerDay);
}

function selectValueToTimesPerDay(value: string): number | null {
  return value === 'prn' ? null : Number(value);
}

export function MedicationEditDialog({
  open,
  medication,
  mode,
  onOpenChange,
  onSave,
  onDelete,
}: MedicationEditDialogProps) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(medication));
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDraft(toDraft(medication));
    setConfirmingDelete(false);
  }, [medication, open]);

  function save() {
    if (!draft.name.trim()) return;
    onSave({
      tempId: medication?.tempId ?? `new_${Date.now()}`,
      name: draft.name.trim(),
      dose: draft.dose.trim(),
      timesPerDay: draft.timesPerDay,
      days: draft.days,
      note: draft.note,
      confidence: medication?.confidence,
    });
  }

  function deleteMedication() {
    onDelete?.();
    setConfirmingDelete(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        variant="sheet"
        aria-describedby={
          confirmingDelete ? 'medication-delete-description' : 'medication-edit-description'
        }
      >
        {confirmingDelete ? (
          <div className="flex flex-col gap-4 pr-10">
            <DialogTitle className="text-xl">이 약을 지울까요?</DialogTitle>
            <DialogDescription id="medication-delete-description" className="text-base">
              {medication?.name ?? '이 약'} 정보가 결과 확인 목록에서 삭제됩니다.
            </DialogDescription>
            <div className="flex flex-col gap-2">
              <Button variant="danger" onClick={deleteMedication}>
                삭제
              </Button>
              <Button variant="secondary" onClick={() => setConfirmingDelete(false)}>
                취소
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="pr-10">
              <DialogTitle className="text-xl">
                {mode === 'add' ? '약 추가' : `${medication?.name ?? '약'} 수정`}
              </DialogTitle>
              <DialogDescription id="medication-edit-description" className="mt-1">
                약봉투와 다른 내용만 고쳐주세요.
              </DialogDescription>
            </div>

            <div className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto pr-1">
              <Input
                label="약품명"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                placeholder="예: 셀레콕시브"
              />
              <Input
                label="용량"
                value={draft.dose}
                onChange={(event) => setDraft({ ...draft, dose: event.target.value })}
                placeholder="예: 200mg"
              />

              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-bold text-foreground">1일 복용 횟수</label>
                <Select
                  value={timesPerDayToSelectValue(draft.timesPerDay)}
                  onValueChange={(value) =>
                    setDraft({ ...draft, timesPerDay: selectValueToTimesPerDay(value) })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIMES_PER_DAY_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Input
                label="복용 일수"
                type="number"
                inputMode="numeric"
                min={1}
                value={draft.days ?? ''}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    days: event.target.value ? Number(event.target.value) : null,
                  })
                }
                placeholder="예: 7"
              />
            </div>

            <Button disabled={!draft.name.trim()} onClick={save}>
              저장
            </Button>

            {mode === 'edit' && onDelete && (
              <button
                type="button"
                className={cn(
                  'min-h-touch text-sm font-bold text-danger-strong',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                )}
                onClick={() => setConfirmingDelete(true)}
              >
                이 약 삭제
              </button>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
