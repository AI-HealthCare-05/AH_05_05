import { useEffect, useState } from 'react';
import type { MedicationOverviewRange } from '@/entities/medication';
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle } from '@/shared/ui';
import {
  type MedicationPeriodPreset,
  presetForRange,
  presetRange,
} from './medicationPeriod';

interface MedicationPeriodFilterSheetProps {
  open: boolean;
  range: MedicationOverviewRange;
  onOpenChange: (open: boolean) => void;
  onApply: (range: MedicationOverviewRange) => void;
}

const OPTIONS: Array<{ value: MedicationPeriodPreset; label: string }> = [
  { value: 'one-month', label: '최근 1개월' },
  { value: 'three-months', label: '최근 3개월' },
  { value: 'six-months', label: '최근 6개월' },
  { value: 'custom', label: '직접 지정' },
];

export function MedicationPeriodFilterSheet({
  open,
  range,
  onOpenChange,
  onApply,
}: MedicationPeriodFilterSheetProps) {
  const [preset, setPreset] = useState<MedicationPeriodPreset>('three-months');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setPreset(presetForRange(range, new Date()));
    setFrom(range.from ?? '');
    setTo(range.to ?? '');
    setError(null);
  }, [open, range]);

  function apply() {
    if (preset === 'three-months') {
      onApply({});
      return;
    }
    if (preset === 'one-month' || preset === 'six-months') {
      onApply(presetRange(preset, new Date()));
      return;
    }
    if (!from || !to) {
      setError('시작일과 종료일을 모두 입력해주세요.');
      return;
    }
    if (from > to) {
      setError('시작일은 종료일보다 늦을 수 없어요.');
      return;
    }
    onApply({ from, to });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" aria-describedby="medication-period-description">
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
                }}
              />
              {option.label}
            </label>
          ))}
        </fieldset>

        {preset === 'custom' && (
          <div className="grid grid-cols-2 gap-3">
            <label className="flex min-w-0 flex-col gap-1 text-sm text-muted-foreground">
              시작일
              <input
                type="date"
                value={from}
                className="min-h-touch min-w-0 rounded-input border border-input bg-card px-3 text-foreground"
                onChange={(event) => {
                  setFrom(event.target.value);
                  setError(null);
                }}
              />
            </label>
            <label className="flex min-w-0 flex-col gap-1 text-sm text-muted-foreground">
              종료일
              <input
                type="date"
                value={to}
                className="min-h-touch min-w-0 rounded-input border border-input bg-card px-3 text-foreground"
                onChange={(event) => {
                  setTo(event.target.value);
                  setError(null);
                }}
              />
            </label>
          </div>
        )}

        {error && <p className="text-sm font-medium text-danger-strong">{error}</p>}
        <Button onClick={apply}>적용</Button>
      </DialogContent>
    </Dialog>
  );
}
