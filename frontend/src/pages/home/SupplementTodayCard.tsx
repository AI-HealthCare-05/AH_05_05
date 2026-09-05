import { useEffect, useRef, useState } from 'react';
import {
  getSupplementDoses, saveSupplementDose,
  type Supplement, type SupplementDoseRecord, type SupplementSlot,
} from '@/entities/supplement';
import { SLOT_ORDER, mealSlotLabel } from '@/shared/model/mealSlot';
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
  function updateRecord(record: SupplementDoseRecord) {
    setRecords(current => [
      ...(current ?? []).filter(item => !(item.supplementId === record.supplementId && item.slot === record.slot)),
      ...(record.taken ? [record] : []),
    ]);
  }

  return (
    <section aria-labelledby="today-supplement-title" className="flex flex-col gap-3">
      <h2 id="today-supplement-title" className="text-2xl font-bold text-foreground">오늘의 영양제</h2>
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
      ) : SLOT_ORDER.map(slot => {
        const items = scheduled.filter(item => item.slots.includes(slot));
        return items.length > 0 ? (
          <SupplementSlotCard
            key={`${date}:${slot}`}
            date={date}
            slot={slot}
            supplements={items}
            records={records}
            onSaved={updateRecord}
          />
        ) : null;
      })}
      <button type="button" className="min-h-touch self-end text-sm font-bold text-primary-strong" onClick={onBrowse}>
        영양제 살펴보기
      </button>
    </section>
  );
}

function SupplementSlotCard({ date, slot, supplements, records, onSaved }: {
  date: string;
  slot: SupplementSlot;
  supplements: Supplement[];
  records: SupplementDoseRecord[];
  onSaved: (record: SupplementDoseRecord) => void;
}) {
  const [selecting, setSelecting] = useState(false);
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
  const targets = selected.length > 0 ? selected : remaining.map(item => item.supplementId);
  const label = selected.length > 0
    ? `${selected.length}개 ${undo ? '되돌리기' : '먹었어요'}`
    : '다 먹었어요';

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
    setSelecting(failures.length > 0);
    setPending(false);
    inFlight.current = false;
  }

  return (
    <Card className="gap-3 p-4">
      <div role="group" aria-label={`${mealSlotLabel(slot, 'short')} 영양제`} className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-bold text-foreground">
            {mealSlotLabel(slot, 'short')} {supplements[0]?.slotTimes?.[slot] ?? ''}
          </h3>
          <button
            type="button" aria-pressed={selecting} disabled={pending}
            className="min-h-touch px-2 text-sm font-bold text-primary-strong disabled:opacity-50"
            onClick={() => { setSelecting(!selecting); setSelected([]); setFailed([]); }}
          >
            {selecting ? '선택 취소' : '개별 선택'}
          </button>
        </div>
        {selecting && (
          <p className="text-sm text-muted-foreground">
            일부만 먹었다면 선택해주세요. 완료한 영양제를 선택하면 기록을 되돌려요.
            완료 항목과 미완료 항목은 따로 선택해요.
          </p>
        )}
        <ul className="flex flex-col gap-2" aria-label={`${mealSlotLabel(slot, 'short')}에 먹을 영양제`}>
          {supplements.map(supplement => {
            const taken = takenIds.has(supplement.supplementId);
            return (
              <li key={supplement.supplementId}>
                <label className={`flex min-h-touch items-center gap-3 ${selecting ? 'cursor-pointer' : ''}`}>
                  {selecting && (
                    <input
                      type="checkbox" aria-label={`${supplement.name} 선택`}
                      checked={selected.includes(supplement.supplementId)} disabled={pending}
                      onChange={() => toggle(supplement.supplementId)} className="size-6 shrink-0 accent-primary"
                    />
                  )}
                  <span className="min-w-0 flex-1 text-base font-bold text-foreground">{supplement.name}</span>
                  <span className="shrink-0 text-sm text-muted-foreground">
                    {supplement.doseAmount}{supplement.doseUnit}
                  </span>
                  {taken && <span className="shrink-0 text-sm font-bold text-primary-strong">복용 완료</span>}
                </label>
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
        ) : (
          <Button
            variant={undo ? 'secondary' : 'primary'} disabled={pending || targets.length === 0}
            onClick={() => void save(targets.map(supplementId => ({ supplementId, date, slot, taken: !undo })))}
          >
            {pending ? '저장 중...' : label}
          </Button>
        )}
      </div>
    </Card>
  );
}
