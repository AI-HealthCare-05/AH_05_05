import { useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
import {
  getSupplementDoses, saveSupplementDose,
  type Supplement, type SupplementDoseRecord, type SupplementSlot,
} from '@/entities/supplement';
import { DEFAULT_MEAL_TIMES, SLOT_ORDER, mealSlotLabel } from '@/shared/model/mealSlot';
import { Button, Card } from '@/shared/ui';

interface Props {
  supplements: Supplement[];
  date: string;
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
  onBrowse: () => void;
}

export function SupplementTodayCard({ supplements, date, loading, loadError, onRetry, onBrowse }: Props) {
  const [records, setRecords] = useState<SupplementDoseRecord[] | null>(null);
  const [recordError, setRecordError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRecords(null);
    setRecordError(false);
    getSupplementDoses(date)
      .then(result => { if (!cancelled) setRecords(result); })
      .catch(() => { if (!cancelled) setRecordError(true); });
    return () => { cancelled = true; };
  }, [date, retryKey]);

  const scheduled = supplements.filter(item =>
    (!item.startDate || item.startDate <= date) && (!item.endDate || item.endDate >= date),
  );
  const supplementSlots = SLOT_ORDER.map(slot => {
    const slotSupplements = scheduled.filter(item => item.slots.includes(slot));
    return {
      slot,
      supplements: slotSupplements,
      time: slotSupplements[0]?.slotTimes?.[slot] || DEFAULT_MEAL_TIMES[slot],
    };
  })
    .filter(item => item.supplements.length > 0)
    .sort((left, right) => timeInMinutes(left.time) - timeInMinutes(right.time));
  const primarySlot = selectPrimarySupplementSlot(supplementSlots, new Date());
  function updateRecord(record: SupplementDoseRecord) {
    setRecords(current => [
      ...(current ?? []).filter(item => !(item.supplementId === record.supplementId && item.slot === record.slot)),
      ...(record.taken ? [record] : []),
    ]);
  }

  return (
    <section aria-label="오늘의 영양제" className="flex flex-col gap-3">
      {loadError || recordError ? (
        <Card className="gap-3 p-4">
          <p role="alert" className="text-sm text-danger-strong">
            {loadError ?? '영양제 복용 기록을 불러오지 못했어요.'}
          </p>
          <Button variant="secondary" onClick={() => { onRetry(); setRetryKey(key => key + 1); }}>
            다시 시도
          </Button>
        </Card>
      ) : loading || records === null ? (
        <p role="status" className="text-sm text-muted-foreground">영양제 복용 정보를 불러오는 중이에요.</p>
      ) : scheduled.length === 0 ? (
        <Card className="p-4"><p className="text-sm text-muted-foreground">오늘 먹을 영양제가 없어요.</p></Card>
      ) : primarySlot ? (
          <SupplementSlotCard
            key={`${date}:${primarySlot.slot}`}
            date={date}
            slot={primarySlot.slot}
            time={primarySlot.time}
            supplements={primarySlot.supplements}
            records={records}
            onSaved={updateRecord}
          />
      ) : null}
      <button type="button" className="min-h-touch self-end text-sm font-bold text-primary-strong" onClick={onBrowse}>
        영양제 살펴보기
      </button>
    </section>
  );
}

function selectPrimarySupplementSlot(
  slots: Array<{ slot: SupplementSlot; supplements: Supplement[]; time: string }>,
  now: Date,
) {
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  return slots.filter(item => timeInMinutes(item.time) <= nowMinutes).at(-1) ?? slots[0];
}

function timeInMinutes(value: string): number {
  const [hours = '0', minutes = '0'] = value.split(':');
  return Number(hours) * 60 + Number(minutes);
}

function SupplementSlotCard({ date, slot, time, supplements, records, onSaved }: {
  date: string;
  slot: SupplementSlot;
  time: string;
  supplements: Supplement[];
  records: SupplementDoseRecord[];
  onSaved: (record: SupplementDoseRecord) => void;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState<SupplementDoseRecord[]>([]);
  const inFlight = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const takenIds = new Set(records.filter(item => item.slot === slot && item.taken).map(item => item.supplementId));
  const remaining = supplements.filter(item => !takenIds.has(item.supplementId));
  const undo = selected.length > 0 && takenIds.has(selected[0]);
  const selectedLabel = selected.length > 0
    ? `${selected.length}개 ${undo ? '되돌리기' : '먹었어요'}`
    : '0개 먹었어요';

  function toggle(id: number) {
    setFailed([]);
    setSelected(current => {
      if (current.includes(id)) return current.filter(item => item !== id);
      if (current.length > 0 && takenIds.has(current[0]) !== takenIds.has(id)) return [id];
      return [...current, id];
    });
  }

  async function save(changes: SupplementDoseRecord[]) {
    if (inFlight.current || changes.length === 0) return;
    inFlight.current = true;
    setPending(true);
    setFailed([]);
    const failures: SupplementDoseRecord[] = [];
    await Promise.all(changes.map(async change => {
      try {
        const result = await saveSupplementDose(change);
        if (alive.current) onSaved(result);
      } catch { failures.push(change); }
    }));
    if (!alive.current) return;
    setFailed(failures);
    setSelected(failures.map(item => item.supplementId));
    setPending(false);
    inFlight.current = false;
  }

  return (
    <Card className="gap-2 p-4">
      <div role="group" aria-label={`${mealSlotLabel(slot, 'short')} 영양제`} className="flex flex-col gap-2">
        <h3 className="text-base font-bold text-foreground">
          {mealSlotLabel(slot, 'short')} {time}
        </h3>
        <ul className="flex flex-col" aria-label={`${mealSlotLabel(slot, 'short')}에 먹을 영양제`}>
          {supplements.map(supplement => {
            const taken = takenIds.has(supplement.supplementId);
            const isSelected = selected.includes(supplement.supplementId);
            return (
              <li key={supplement.supplementId}>
                <button
                  type="button"
                  aria-label={`${supplement.name} 선택`}
                  aria-pressed={isSelected}
                  disabled={pending}
                  className="flex min-h-touch w-full min-w-0 items-center gap-3 rounded-control text-left focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-50"
                  onClick={() => toggle(supplement.supplementId)}
                >
                  <span
                    data-supplement-selection-indicator
                    aria-hidden
                    className={`flex size-6 shrink-0 items-center justify-center rounded-full border ${
                      taken || isSelected
                        ? 'border-primary bg-primary text-card'
                        : 'border-border bg-card text-transparent'
                    }`}
                  >
                    {(taken || isSelected) && <Check className="size-4" strokeWidth={3} />}
                  </span>
                  <span className="min-w-0 flex-1 text-base font-bold text-foreground">{supplement.name}</span>
                  <span className="shrink-0 text-sm text-muted-foreground">
                    {supplement.doseAmount}{supplement.doseUnit}
                  </span>
                  {taken && <span className="sr-only">복용 완료</span>}
                </button>
              </li>
            );
          })}
        </ul>
        {failed.length > 0 ? (
          <div className="flex flex-col gap-2">
            <p role="alert" className="text-sm text-danger-strong">
              {failed.length}개 영양제의 복용 기록을 저장하지 못했어요. 다시 시도해주세요.
            </p>
            <Button variant="secondary" disabled={pending} onClick={() => void save(failed)}>다시 시도</Button>
          </div>
        ) : null}
        <div data-supplement-actions className="grid grid-cols-2 gap-2">
          <Button
            fullWidth={false}
            variant="secondary"
            disabled={pending || selected.length === 0}
            className="w-full px-2"
            onClick={() => void save(selected.map(supplementId => ({ supplementId, date, slot, taken: !undo })))}
          >
            {pending && selected.length > 0 ? '저장 중...' : selectedLabel}
          </Button>
          <Button
            fullWidth={false}
            variant="primary"
            disabled={pending || remaining.length === 0}
            className="w-full px-2"
            onClick={() => void save(remaining.map(item => ({
              supplementId: item.supplementId, date, slot, taken: true,
            })))}
          >
            {pending && selected.length === 0 ? '저장 중...' : '다 먹었어요'}
          </Button>
        </div>
      </div>
    </Card>
  );
}
