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
 * 사용자가 열어보지 않은 약도 OCR의 효능·복용 방법·주의사항을 그대로 보존합니다.
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
  efficacy: string;
  administration: string;
  precautions: string;
  timesPerDay: number | null;
  days: number | null;
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
  efficacy: '',
  administration: '',
  precautions: '',
  timesPerDay: 1,
  days: 1,
};

function toDraft(medication: OcrMedication | null): Draft {
  if (!medication) return EMPTY_DRAFT;
  return {
    name: medication.name,
    dose: medication.dose,
    efficacy: medication.efficacy,
    administration: medication.administration,
    precautions: medication.precautions,
    timesPerDay: medication.timesPerDay,
    days: medication.days,
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
      efficacy: draft.efficacy.trim(),
      administration: draft.administration.trim(),
      precautions: draft.precautions.trim(),
      timesPerDay: draft.timesPerDay,
      days: draft.days,
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
              <Input
                label="효능"
                value={draft.efficacy}
                onChange={(event) => setDraft({ ...draft, efficacy: event.target.value })}
                placeholder="예: 염증과 통증 완화"
              />
              <Input
                label="복용 방법"
                value={draft.administration}
                onChange={(event) => setDraft({ ...draft, administration: event.target.value })}
                placeholder="예: 아침·저녁 식후"
              />
              <Input
                label="주의사항"
                value={draft.precautions}
                onChange={(event) => setDraft({ ...draft, precautions: event.target.value })}
                placeholder="예: 음주를 피하세요"
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
