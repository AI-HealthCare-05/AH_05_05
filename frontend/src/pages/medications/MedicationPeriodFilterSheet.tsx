import { useEffect, useRef, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import type { MedicationOverviewRange } from '@/entities/medication';
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle, Input } from '@/shared/ui';
import {
  addCalendarYears,
  localIsoDate,
  type MedicationPeriodPreset,
  presetForRange,
  presetRange,
} from './medicationPeriod';
import { MedicationPeriodCalendar } from './MedicationPeriodCalendar';

interface MedicationPeriodFilterSheetProps {
  open: boolean;
  range: MedicationOverviewRange;
  onOpenChange: (open: boolean) => void;
  onApply: (range: MedicationOverviewRange) => void;
}

const OPTIONS: Array<{ value: MedicationPeriodPreset; label: string }> = [
  { value: 'three-months', label: '최근 3개월' },
  { value: 'six-months', label: '최근 6개월' },
  { value: 'one-year', label: '최근 1년' },
  { value: 'custom', label: '직접 지정' },
];

function isStrictIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
}

function formatIsoDateEntry(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
}

export function MedicationPeriodFilterSheet({
  open,
  range,
  onOpenChange,
  onApply,
}: MedicationPeriodFilterSheetProps) {
  const [preset, setPreset] = useState<MedicationPeriodPreset>('six-months');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [openCalendar, setOpenCalendar] = useState<'from' | 'to' | null>(null);
  const fromCalendarButtonRef = useRef<HTMLButtonElement>(null);
  const toCalendarButtonRef = useRef<HTMLButtonElement>(null);
  const today = localIsoDate(new Date());
  const earliestDate = addCalendarYears(today, -2);

  useEffect(() => {
    if (!open) return;
    setPreset(presetForRange(range, new Date()));
    setFrom(range.from ?? '');
    setTo(range.to ?? '');
    setError(null);
    setOpenCalendar(null);
  }, [open, range]);

  function closeCalendar(field: 'from' | 'to') {
    setOpenCalendar(null);
    window.requestAnimationFrame(() => {
      (field === 'from' ? fromCalendarButtonRef : toCalendarButtonRef).current?.focus();
    });
  }

  function apply() {
    if (preset === 'six-months') {
      onApply({});
      return;
    }
    if (preset === 'three-months' || preset === 'one-year') {
      onApply(presetRange(preset, new Date()));
      return;
    }
    if (!from || !to) {
      setError('시작일과 종료일을 모두 입력해주세요.');
      return;
    }
    if (!isStrictIsoDate(from) || !isStrictIsoDate(to)) {
      setError('날짜는 YYYY-MM-DD 형식으로 입력해주세요.');
      return;
    }
    if (from > to) {
      setError('시작일은 종료일보다 늦을 수 없어요.');
      return;
    }
    if (from < earliestDate || to > today) {
      setError('조회 기간은 오늘부터 과거 2년까지만 선택할 수 있어요.');
      return;
    }
    onApply({ from, to });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        variant="sheet"
        aria-describedby="medication-period-description"
        className="max-h-[calc(100dvh-1rem)] overflow-y-auto overscroll-contain"
      >
        <div className="pr-10">
          <DialogTitle className="text-xl">조회 기간</DialogTitle>
          <DialogDescription id="medication-period-description" className="mt-1">
            처방을 등록한 기간을 선택해주세요.
          </DialogDescription>
        </div>

        <fieldset className="grid grid-cols-2 gap-2">
          <legend className="sr-only">조회 기간 선택</legend>
          {OPTIONS.map((option) => (
            <label
              key={option.value}
              className={`flex min-h-touch cursor-pointer items-center justify-center rounded-input border px-3 text-sm font-bold ${
                preset === option.value
                  ? 'border-primary bg-primary-bg text-primary-strong'
                  : 'border-border bg-card text-muted-foreground'
              }`}
            >
              <input
                type="radio"
                name="medication-period"
                value={option.value}
                checked={preset === option.value}
                className="sr-only"
                onChange={() => {
                  setPreset(option.value);
                  setError(null);
                  setOpenCalendar(null);
                }}
              />
              {option.label}
            </label>
          ))}
        </fieldset>

        {preset === 'custom' && (
          <>
            {openCalendar === 'from' && (
              <MedicationPeriodCalendar
                label="시작일"
                value={from}
                min={earliestDate}
                max={to && isStrictIsoDate(to) && to < today ? to : today}
                onSelect={(date) => {
                  setFrom(date);
                  setError(null);
                  closeCalendar('from');
                }}
                onClose={() => closeCalendar('from')}
              />
            )}
            {openCalendar === 'to' && (
              <MedicationPeriodCalendar
                label="종료일"
                value={to}
                min={from && isStrictIsoDate(from) && from > earliestDate ? from : earliestDate}
                max={today}
                onSelect={(date) => {
                  setTo(date);
                  setError(null);
                  closeCalendar('to');
                }}
                onClose={() => closeCalendar('to')}
              />
            )}
            <div className="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2">
              <Input
                label="시작일"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                placeholder="YYYY-MM-DD"
                pattern="\d{4}-\d{2}-\d{2}"
                maxLength={10}
                value={from}
                min={earliestDate}
                max={to && isStrictIsoDate(to) && to < today ? to : today}
                className="min-w-0 [&_input]:min-w-0"
                trailingAction={
                  <button
                    ref={fromCalendarButtonRef}
                    type="button"
                    aria-label="시작일 달력 열기"
                    aria-expanded={openCalendar === 'from'}
                    className="flex size-touch items-center justify-center rounded-input text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => setOpenCalendar((current) => (current === 'from' ? null : 'from'))}
                  >
                    <CalendarDays aria-hidden className="size-5" />
                  </button>
                }
                onChange={(event) => {
                  setFrom(formatIsoDateEntry(event.target.value));
                  setError(null);
                }}
              />
              <Input
                label="종료일"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                placeholder="YYYY-MM-DD"
                pattern="\d{4}-\d{2}-\d{2}"
                maxLength={10}
                value={to}
                min={from && isStrictIsoDate(from) && from > earliestDate ? from : earliestDate}
                max={today}
                className="min-w-0 [&_input]:min-w-0"
                trailingAction={
                  <button
                    ref={toCalendarButtonRef}
                    type="button"
                    aria-label="종료일 달력 열기"
                    aria-expanded={openCalendar === 'to'}
                    className="flex size-touch items-center justify-center rounded-input text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => setOpenCalendar((current) => (current === 'to' ? null : 'to'))}
                  >
                    <CalendarDays aria-hidden className="size-5" />
                  </button>
                }
                onChange={(event) => {
                  setTo(formatIsoDateEntry(event.target.value));
                  setError(null);
                }}
              />
            </div>
          </>
        )}

        {error && <p className="text-sm font-medium text-danger-strong">{error}</p>}
        <Button onClick={apply}>적용</Button>
      </DialogContent>
    </Dialog>
  );
}
