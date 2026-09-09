import { useEffect, useRef, useState } from 'react';
import type { FollowUpVisit, FollowUpVisitInput } from '@/entities/follow-up-visit';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  TimePickerSheet,
} from '@/shared/ui';

function tomorrowString(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const year = Number(parts.find((part) => part.type === 'year')?.value);
  const month = Number(parts.find((part) => part.type === 'month')?.value);
  const day = Number(parts.find((part) => part.type === 'day')?.value);
  const tomorrow = new Date(Date.UTC(year, month - 1, day + 1));
  const nextMonth = String(tomorrow.getUTCMonth() + 1).padStart(2, '0');
  const nextDay = String(tomorrow.getUTCDate()).padStart(2, '0');
  return `${tomorrow.getUTCFullYear()}-${nextMonth}-${nextDay}`;
}

function isTenMinuteTime(value: string): boolean {
  return /^(?:[01]\d|2[0-3]):(?:00|10|20|30|40|50)$/.test(value);
}

interface FollowUpVisitSheetProps {
  open: boolean;
  visit: FollowUpVisit | null;
  onOpenChange: (open: boolean) => void;
  onSave: (input: FollowUpVisitInput) => Promise<void>;
  onDelete: (visit: FollowUpVisit) => void;
}

export function FollowUpVisitSheet({
  open,
  visit,
  onOpenChange,
  onSave,
  onDelete,
}: FollowUpVisitSheetProps) {
  const [visitDate, setVisitDate] = useState('');
  const [visitTime, setVisitTime] = useState('');
  const [hospital, setHospital] = useState('');
  const [saving, setSaving] = useState(false);
  const [timePickerOpen, setTimePickerOpen] = useState(false);
  const [focusVisitDateAfterValidation, setFocusVisitDateAfterValidation] = useState(false);
  const visitDateInputRef = useRef<HTMLInputElement>(null);
  const [minimumVisitDate, setMinimumVisitDate] = useState(tomorrowString);
  const dateError =
    visitDate && visitDate < minimumVisitDate
      ? '진료일은 내일부터 선택해주세요.'
      : undefined;
  const timeError =
    visitTime && !isTenMinuteTime(visitTime)
      ? '진료 시간은 10분 단위로 선택해주세요.'
      : undefined;
  const canSave = Boolean(visitDate) && Boolean(hospital.trim()) && !dateError && !timeError;

  useEffect(() => {
    if (!open) return;
    setVisitDate(visit?.visitDate ?? '');
    setVisitTime(visit?.visitTime ?? '');
    setHospital(visit?.hospital ?? '');
    setSaving(false);
    setTimePickerOpen(false);
    setFocusVisitDateAfterValidation(false);
    setMinimumVisitDate(tomorrowString());
  }, [open, visit]);

  useEffect(() => {
    if (!focusVisitDateAfterValidation || !dateError) return;
    visitDateInputRef.current?.focus();
    setFocusVisitDateAfterValidation(false);
  }, [dateError, focusVisitDateAfterValidation]);

  async function save() {
    const trimmedHospital = hospital.trim();
    const currentMinimumVisitDate = tomorrowString();
    if (currentMinimumVisitDate !== minimumVisitDate) {
      setMinimumVisitDate(currentMinimumVisitDate);
    }
    const invalidDate = !visitDate || visitDate < currentMinimumVisitDate;
    const invalidTime = Boolean(visitTime) && !isTenMinuteTime(visitTime);
    if (invalidDate) {
      setFocusVisitDateAfterValidation(true);
      return;
    }
    if (!trimmedHospital || invalidTime || saving) return;
    setSaving(true);
    try {
      await onSave({
        visitDate,
        visitTime: visitTime || null,
        hospital: trimmedHospital,
      });
      onOpenChange(false);
    } catch {
      // 부모 화면의 ErrorDialog가 실패 내용을 보여주고 시트는 그대로 유지합니다.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" className="max-h-[90dvh] overflow-y-auto">
        <div aria-hidden className="mx-auto h-1 w-10 rounded-pill bg-border" />
        <DialogHeader>
          <DialogTitle>{visit ? '진료일정 수정' : '진료일정 추가'}</DialogTitle>
          <DialogDescription>진료일과 병원명은 필수예요. 시간은 나중에 정해도 돼요.</DialogDescription>
        </DialogHeader>
        <Input
          label="진료일"
          type="date"
          min={minimumVisitDate}
          value={visitDate}
          error={dateError}
          inputRef={visitDateInputRef}
          onChange={(event) => setVisitDate(event.target.value)}
        />
        <div className="flex w-full flex-col gap-1">
          <span className="text-sm font-bold text-foreground">진료 시간</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label={`진료 시간 ${visitTime || '시간 미정'}`}
              aria-invalid={timeError ? true : undefined}
              aria-describedby={timeError ? 'follow-up-visit-time-error' : undefined}
              className={`h-control min-w-0 flex-1 rounded-input border bg-card px-3.5 text-left text-[length:var(--text-control)] focus:outline-none focus:ring-2 focus:ring-ring ${
                timeError ? 'border-danger' : 'border-input'
              } ${visitTime ? 'text-foreground' : 'text-tertiary-foreground'}`}
              onClick={() => setTimePickerOpen(true)}
            >
              {visitTime || '시간 미정'}
            </button>
            {visitTime && (
              <button
                type="button"
                className="min-h-touch shrink-0 px-2 text-sm font-bold text-primary-strong"
                onClick={() => setVisitTime('')}
              >
                시간 지우기
              </button>
            )}
          </div>
          {timeError && (
            <p id="follow-up-visit-time-error" className="text-sm text-danger-strong">
              {timeError}
            </p>
          )}
        </div>
        <Input
          label="병원명 (필수)"
          required
          maxLength={255}
          placeholder="병원명 또는 진료과"
          hint="예: ○○이비인후과 또는 내과"
          value={hospital}
          onChange={(event) => setHospital(event.target.value)}
        />
        <DialogFooter className="pt-2">
          <Button disabled={!canSave || saving} onClick={() => void save()}>
            {saving ? '저장 중...' : '저장'}
          </Button>
          {visit && (
            <Button
              variant="secondary"
              className="text-danger-strong"
              disabled={saving}
              onClick={() => onDelete(visit)}
            >
              삭제
            </Button>
          )}
        </DialogFooter>
        <TimePickerSheet
          open={timePickerOpen}
          description="진료 시간"
          value={visitTime || '08:00'}
          minuteStep={10}
          preserveInvalidMinute
          onApply={(time) => {
            setVisitTime(time);
            setTimePickerOpen(false);
          }}
          onCancel={() => setTimePickerOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
