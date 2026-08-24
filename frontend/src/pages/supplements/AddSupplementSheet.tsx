import { useState } from 'react';
import { ScanLine, Search } from 'lucide-react';
import type { AddSupplementPayload, SupplementTime } from '@/entities/supplement';
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle, Input } from '@/shared/ui';
import { cn } from '@/shared/lib/cn';

interface AddSupplementSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (payload: AddSupplementPayload) => Promise<void>;
}

const TIMES: SupplementTime[] = ['아침', '점심', '저녁'];

export function AddSupplementSheet({ open, onOpenChange, onSave }: AddSupplementSheetProps) {
  const [name, setName] = useState('');
  const [dailyCount, setDailyCount] = useState(1);
  const [times, setTimes] = useState<SupplementTime[]>(['아침']);
  const [saving, setSaving] = useState(false);

  function toggleTime(time: SupplementTime) {
    setTimes((current) =>
      current.includes(time) ? current.filter((item) => item !== time) : [...current, time],
    );
  }

  async function save() {
    if (!name.trim() || dailyCount < 1 || times.length === 0 || saving) return;
    setSaving(true);
    try {
      await onSave({ name: name.trim(), dailyCount, times });
      setName('');
      setDailyCount(1);
      setTimes(['아침']);
      onOpenChange(false);
    } catch {
      // 저장 실패 문구와 재시도 동작은 화면의 ErrorDialog가 한 곳에서 관리합니다.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" aria-describedby="supplement-add-description">
        <div className="pr-10">
          <DialogTitle className="text-xl">영양제 추가</DialogTitle>
          <DialogDescription id="supplement-add-description" className="mt-1">
            제품명을 먼저 검색해 주세요. 바코드는 보조 수단입니다.
          </DialogDescription>
        </div>

        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute top-10 left-3.5 size-5 text-disabled-foreground" />
            <Input
              label="제품 검색"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="제품명을 입력해 주세요"
              className="[&_input]:pl-11"
            />
          </div>
          <Button variant="secondary">
            <ScanLine aria-hidden className="mr-2 size-5" />
            바코드로 찾기
          </Button>
          <Input
            label="1일 정수"
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            value={dailyCount}
            onChange={(event) => setDailyCount(Number(event.target.value))}
          />
          <fieldset>
            <legend className="mb-2 text-sm font-bold text-foreground">먹는 시간대</legend>
            <div className="grid grid-cols-3 gap-2">
              {TIMES.map((time) => {
                const selected = times.includes(time);
                return (
                  <button
                    key={time}
                    type="button"
                    aria-pressed={selected}
                    className={cn(
                      'min-h-touch rounded-input border text-sm font-bold',
                      selected
                        ? 'border-primary bg-primary-bg text-primary-strong'
                        : 'border-border bg-card text-muted-foreground',
                    )}
                    onClick={() => toggleTime(time)}
                  >
                    {time}
                  </button>
                );
              })}
            </div>
          </fieldset>
        </div>

        <Button disabled={!name.trim() || dailyCount < 1 || times.length === 0 || saving} onClick={save}>
          {saving ? '추가 중...' : '추가하기'}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
