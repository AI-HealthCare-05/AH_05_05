import type { DoseRecord, MealSlot, MedicationOverview } from '@/entities/medication';
import { mealSlotLabel, SLOT_ORDER } from '@/shared/model/mealSlot';
import { Card } from '@/shared/ui';

interface MedicationRecordGridProps {
  overviews: MedicationOverview[];
  records: DoseRecord[];
  now: Date;
  animatedRecordKey?: string | null;
  onMarkTaken: (date: string, slot: MealSlot, recordIds: number[]) => void;
}

type RecordCellState = 'taken' | 'missing' | 'future' | 'empty';

export function MedicationRecordGrid({
  overviews,
  records,
  now,
  animatedRecordKey,
  onMarkTaken,
}: MedicationRecordGridProps) {
  const dates = getDateRange(
    overviews.map((overview) => overview.start.date).sort()[0] ?? '',
    overviews.map((overview) => overview.endDate).sort().at(-1) ?? '',
  );
  const slots = SLOT_ORDER.filter((slot) =>
    overviews.some((overview) =>
      overview.medications.some(
        (medication) => !medication.asNeeded && medication.slots.includes(slot),
      ),
    ),
  );
  const takenRecords = new Set(
    records
      .filter((record) => record.taken)
      .map((record) => `${record.recordId}:${record.date}:${record.slot}`),
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
              {formatPeriod(dates[0] ?? '', dates.at(-1) ?? '')}
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
              <div key={slot} role="row" aria-label={mealSlotLabel(slot)} className="contents">
                <span
                  role="rowheader"
                  className="self-center whitespace-nowrap text-sm text-muted-foreground"
                >
                  {mealSlotLabel(slot)}
                </span>
                {dates.map((date) => {
                  const recordIds = episodeTargetsForCell(overviews, date, slot);
                  const state = getCellState({
                    overviews,
                    date,
                    slot,
                    recordIds,
                    now,
                    takenRecords,
                  });
                  const label = `${formatDateLabel(date)} ${mealSlotLabel(slot)} ${CELL_LABEL[state]}`;

                  if (state === 'missing') {
                    return (
                      <button
                        key={date}
                        type="button"
                        role="gridcell"
                        aria-label={label}
                        className="h-record-cell-h min-w-0 rounded-record-cell bg-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => onMarkTaken(date, slot, recordIds)}
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
                      className={`h-record-cell-h min-w-0 rounded-record-cell ${CELL_CLASS[state]} ${
                        state === 'taken' && animatedRecordKey === `${date}:${slot}`
                          ? 'origin-bottom animate-record-grow motion-reduce:animate-none'
                          : ''
                      }`}
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
  overviews,
  date,
  slot,
  recordIds,
  now,
  takenRecords,
}: {
  overviews: MedicationOverview[];
  date: string;
  slot: MealSlot;
  recordIds: number[];
  now: Date;
  takenRecords: Set<string>;
}): RecordCellState {
  if (recordIds.length === 0) return 'empty';
  const allTaken = recordIds.every((recordId) =>
    takenRecords.has(`${recordId}:${date}:${slot}`),
  );
  if (allTaken) return 'taken';
  const overview = overviews.find((item) => recordIds.includes(item.recordId));
  return overview && hasSlotTimePassed(date, slot, overview, now) ? 'missing' : 'future';
}

function episodeTargetsForCell(
  overviews: MedicationOverview[],
  date: string,
  slot: MealSlot,
): number[] {
  return overviews
    .filter((overview) => {
      const dateIndex = daysBetween(overview.start.date, date);
      return overview.medications.some(
        (medication) =>
          !medication.asNeeded &&
          medication.slots.includes(slot) &&
          dateIndex >= 0 &&
          dateIndex < medication.days,
      );
    })
    .map((overview) => overview.recordId);
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
  if (!from || !to) return [];
  const start = parseLocalDate(from);
  const end = parseLocalDate(to);
  const dates: string[] = [];
  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    dates.push(formatLocalIsoDate(cursor));
  }
  return dates;
}

function daysBetween(from: string, to: string): number {
  return Math.round((parseLocalDate(to).getTime() - parseLocalDate(from).getTime()) / 86_400_000);
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
  if (!from || !to) return '';
  const [, fromMonth, fromDay] = from.split('-').map(Number);
  const [, toMonth, toDay] = to.split('-').map(Number);
  return fromMonth === toMonth
    ? `${fromMonth}월 ${fromDay}일 ~ ${toDay}일`
    : `${fromMonth}월 ${fromDay}일 ~ ${toMonth}월 ${toDay}일`;
}
