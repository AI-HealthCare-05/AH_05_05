import type {
  DoseRecord,
  MealSlot,
  MedicationOverview,
} from '@/entities/medication';
import { Card } from '@/shared/ui';

const SLOT_ORDER: MealSlot[] = ['morning', 'lunch', 'evening', 'bedtime'];

const SLOT_LABEL: Record<MealSlot, string> = {
  morning: '아침',
  lunch: '점심',
  evening: '저녁',
  bedtime: '취침 전',
};

interface MedicationRecordGridProps {
  overview: MedicationOverview;
  records: DoseRecord[];
  now: Date;
  onMarkTaken: (date: string, slot: MealSlot) => void;
}

type RecordCellState = 'taken' | 'missing' | 'future' | 'empty';

export function MedicationRecordGrid({
  overview,
  records,
  now,
  onMarkTaken,
}: MedicationRecordGridProps) {
  const dates = getDateRange(overview.start.date, overview.endDate);
  const slots = SLOT_ORDER.filter((slot) =>
    overview.medications.some(
      (medication) => !medication.asNeeded && medication.slots.includes(slot),
    ),
  );
  const takenRecords = new Set(
    records.filter((record) => record.taken).map((record) => `${record.date}:${record.slot}`),
  );
  const today = formatLocalIsoDate(now);
  const gridTemplateColumns = `minmax(2.75rem, auto) repeat(${dates.length}, minmax(0, var(--spacing-record-cell-w)))`;

  return (
    <section aria-label="복약 기록">
      <Card className="overflow-hidden p-4">
        <div className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-xl font-bold text-foreground">복약 기록</h2>
            <p className="text-sm text-muted-foreground tnum">
              {formatPeriod(overview.start.date, overview.endDate)}
            </p>
          </div>

          <div
            role="grid"
            aria-label="복약 기간 기록"
            className="grid w-full gap-x-record-gap gap-y-record-gap overflow-hidden"
            style={{ gridTemplateColumns }}
          >
            <span aria-hidden />
            {dates.map((date) => (
              <span
                key={date}
                role="columnheader"
                aria-label={formatDateLabel(date)}
                className={`min-w-0 text-center text-sm tnum ${
                  date === today
                    ? 'font-bold text-foreground'
                    : 'font-normal text-disabled-foreground'
                }`}
              >
                {Number(date.slice(8, 10))}
              </span>
            ))}

            {slots.map((slot) => (
              <div key={slot} role="row" aria-label={SLOT_LABEL[slot]} className="contents">
                <span
                  role="rowheader"
                  className="self-center whitespace-nowrap text-sm text-muted-foreground"
                >
                  {SLOT_LABEL[slot]}
                </span>
                {dates.map((date, dateIndex) => {
                  const state = getCellState({
                    overview,
                    date,
                    dateIndex,
                    slot,
                    now,
                    takenRecords,
                  });
                  const label = `${formatDateLabel(date)} ${SLOT_LABEL[slot]} ${CELL_LABEL[state]}`;

                  if (state === 'missing') {
                    return (
                      <button
                        key={date}
                        type="button"
                        role="gridcell"
                        aria-label={label}
                        className="h-record-cell-h min-w-0 rounded-record-cell bg-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => onMarkTaken(date, slot)}
                      />
                    );
                  }

                  if (state === 'future') {
                    return (
                      <button
                        key={date}
                        type="button"
                        role="gridcell"
                        aria-label={label}
                        disabled
                        className="h-record-cell-h min-w-0 rounded-record-cell bg-muted-bg"
                      />
                    );
                  }

                  return (
                    <span
                      key={date}
                      role="gridcell"
                      aria-label={label}
                      className={`h-record-cell-h min-w-0 rounded-record-cell ${CELL_CLASS[state]}`}
                    />
                  );
                })}
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-muted-foreground">
            <Legend colorClass="bg-primary" label="먹은 기록" />
            <Legend colorClass="bg-border" label="기록 없음" />
            <Legend colorClass="bg-muted-bg" label="아직" />
          </div>
        </div>
      </Card>
    </section>
  );
}

function Legend({ colorClass, label }: { colorClass: string; label: string }) {
  return (
    <span className="flex items-center gap-2">
      <span aria-hidden className={`size-3 rounded-record-cell ${colorClass}`} />
      {label}
    </span>
  );
}

const CELL_LABEL: Record<RecordCellState, string> = {
  taken: '먹은 기록',
  missing: '기록 없음',
  future: '아직',
  empty: '약 없음',
};

const CELL_CLASS: Record<Exclude<RecordCellState, 'missing'>, string> = {
  taken: 'bg-primary',
  future: 'bg-muted-bg',
  empty: 'bg-transparent',
};

function getCellState({
  overview,
  date,
  dateIndex,
  slot,
  now,
  takenRecords,
}: {
  overview: MedicationOverview;
  date: string;
  dateIndex: number;
  slot: MealSlot;
  now: Date;
  takenRecords: Set<string>;
}): RecordCellState {
  const hasMedication = overview.medications.some(
    (medication) =>
      !medication.asNeeded &&
      medication.slots.includes(slot) &&
      dateIndex < medication.days,
  );
  if (!hasMedication) return 'empty';
  if (takenRecords.has(`${date}:${slot}`)) return 'taken';
  return hasSlotTimePassed(date, slot, overview, now) ? 'missing' : 'future';
}

function hasSlotTimePassed(
  date: string,
  slot: MealSlot,
  overview: MedicationOverview,
  now: Date,
): boolean {
  const today = formatLocalIsoDate(now);
  if (date < today) return true;
  if (date > today) return false;

  const [hours, minutes] = overview.mealTimes[slot].split(':').map(Number);
  return now.getHours() * 60 + now.getMinutes() >= hours * 60 + minutes;
}

function getDateRange(from: string, to: string): string[] {
  const start = parseLocalDate(from);
  const end = parseLocalDate(to);
  const dates: string[] = [];
  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    dates.push(formatLocalIsoDate(cursor));
  }
  return dates;
}

function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

function formatLocalIsoDate(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

function formatDateLabel(value: string): string {
  const [, month, day] = value.split('-').map(Number);
  return `${month}월 ${day}일`;
}

function formatPeriod(from: string, to: string): string {
  const [, fromMonth, fromDay] = from.split('-').map(Number);
  const [, toMonth, toDay] = to.split('-').map(Number);
  return fromMonth === toMonth
    ? `${fromMonth}월 ${fromDay}일 ~ ${toDay}일`
    : `${fromMonth}월 ${fromDay}일 ~ ${toMonth}월 ${toDay}일`;
}
