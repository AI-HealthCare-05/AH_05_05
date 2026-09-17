import { useEffect, useState } from 'react';
import type { EditableOcrMedication } from '@/entities/document/types';
import {
  isValidMedicationRegistrationDays,
  isValidMedicationRegistrationFrequency,
} from '@/entities/document/medicationRegistrationValidation';
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
 * OCR에서 읽지 못한 선택 필드는 빈 입력으로 열며, 저장할 때 JSON 키도 생략합니다.
 */

export interface MedicationEditDialogProps {
  open: boolean;
  medication: EditableOcrMedication | null;
  mode: 'add' | 'edit';
  onOpenChange: (open: boolean) => void;
  onSave: (medication: EditableOcrMedication) => void;
  onDelete?: () => void;
}

interface Draft {
  name: string;
  strength: string;
  doseQuantity: string;
  timesPerDay: number | null | undefined;
  days: string;
}

const TIMES_PER_DAY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '1', label: '1회' },
  { value: '2', label: '2회' },
  { value: '3', label: '3회' },
  { value: '4', label: '4회' },
  { value: '5', label: '5회' },
  { value: '6', label: '6회' },
  { value: 'prn', label: '필요 시' },
  { value: 'unread', label: '미추출' },
];

const EMPTY_DRAFT: Draft = {
  name: '',
  strength: '',
  doseQuantity: '',
  timesPerDay: undefined,
  days: '',
};

function toDraft(medication: EditableOcrMedication | null): Draft {
  if (!medication) return EMPTY_DRAFT;
  return {
    name: medication.name,
    strength: medication.strength ?? '',
    doseQuantity: medication.doseQuantity ?? '',
    timesPerDay: medication.timesPerDay,
    days: medication.days === undefined ? '' : String(medication.days),
  };
}

function timesPerDayToSelectValue(timesPerDay: number | null | undefined): string {
  if (timesPerDay === undefined) return 'unread';
  return timesPerDay === null ? 'prn' : String(timesPerDay);
}

function selectValueToTimesPerDay(value: string): number | null | undefined {
  if (value === 'unread') return undefined;
  return value === 'prn' ? null : Number(value);
}

function parsePositiveDecimal(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function parsePositiveInteger(value: string): number | undefined {
  const parsed = parsePositiveDecimal(value);
  return parsed !== undefined && Number.isSafeInteger(parsed) ? parsed : undefined;
}

function nextDaysValue(current: string, next: string): string {
  if (!/^\d{0,3}$/.test(next)) return current;
  return next && Number(next) > 365 ? current : next;
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
  const parsedDays = parsePositiveInteger(draft.days);
  const hasName = Boolean(draft.name.trim());
  const hasValidDays = isValidMedicationRegistrationDays(parsedDays);
  const hasValidFrequency = isValidMedicationRegistrationFrequency(draft.timesPerDay);
  const canSave = hasName && hasValidDays && hasValidFrequency;

  useEffect(() => {
    if (!open) return;
    setDraft(toDraft(medication));
    setConfirmingDelete(false);
  }, [medication, open]);

  function save() {
    if (!canSave || parsedDays === undefined) return;
    const doseQuantity = draft.doseQuantity.trim();
    onSave({
      tempId: medication?.tempId ?? `new_${Date.now()}`,
      name: draft.name,
      ...(draft.strength.trim() ? { strength: draft.strength.trim() } : {}),
      ...(doseQuantity ? { doseQuantity } : {}),
      ...(draft.timesPerDay !== undefined ? { timesPerDay: draft.timesPerDay } : {}),
      days: parsedDays,
      ...(medication?.confidence ? { confidence: medication.confidence } : {}),
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
          confirmingDelete
            ? 'medication-delete-description'
            : mode === 'edit'
              ? 'medication-edit-description'
              : undefined
        }
      >
        {confirmingDelete ? (
          <div className="flex flex-col gap-4">
            <DialogTitle className="pr-10 text-xl">이 약을 지울까요?</DialogTitle>
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
              {mode === 'edit' && (
                <DialogDescription id="medication-edit-description" className="mt-1">
                  약봉투와 다른 내용만 고쳐주세요.
                </DialogDescription>
              )}
            </div>

            <div className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto px-1">
              <Input
                label="약품명"
                value={draft.name}
                maxLength={100}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                placeholder="예: 셀레콕시브"
                error={hasName ? undefined : '약품명을 입력해주세요.'}
              />
              <Input
                label="함량"
                value={draft.strength}
                maxLength={50}
                onChange={(event) => setDraft({ ...draft, strength: event.target.value })}
                placeholder="예: 200mg"
              />
              <Input
                label="1회 투약량"
                value={draft.doseQuantity}
                maxLength={50}
                onChange={(event) => setDraft({ ...draft, doseQuantity: event.target.value })}
                placeholder="예: 1 또는 0.5정"
              />

              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-bold text-foreground">1일 복용 횟수</label>
                <Select
                  value={timesPerDayToSelectValue(draft.timesPerDay)}
                  onValueChange={(value) =>
                    setDraft({ ...draft, timesPerDay: selectValueToTimesPerDay(value) })
                  }
                >
                  <SelectTrigger
                    aria-invalid={!hasValidFrequency || undefined}
                    className={!hasValidFrequency ? 'border-danger' : undefined}
                  >
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
                {!hasValidFrequency && (
                  <p className="text-sm text-danger-strong">1일 복용 횟수 또는 필요 시를 선택해주세요.</p>
                )}
              </div>

              <Input
                label="복용 일수"
                type="text"
                inputMode="numeric"
                maxLength={3}
                pattern="[0-9]*"
                value={draft.days ?? ''}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    days: nextDaysValue(draft.days, event.target.value),
                  })
                }
                placeholder="예: 7"
                error={hasValidDays ? undefined : '복용 일수는 1일에서 365일 사이로 입력해주세요.'}
              />
            </div>

            <Button disabled={!canSave} onClick={save}>
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
