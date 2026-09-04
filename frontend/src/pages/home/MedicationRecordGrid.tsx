import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { DoseRecord, MealSlot, MedicationOverview } from '@/entities/medication';
import { formatDateLabel, formatDatePeriod } from '@/shared/lib/dateLabel';
import { mealSlotLabel, SLOT_ORDER } from '@/shared/model/mealSlot';
import { Card } from '@/shared/ui';

const DAYS_PER_PAGE = 10;

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
  const allDates = getDateRange(
    overviews.map((overview) => overview.start.date).sort()[0] ?? '',
    overviews.map((overview) => overview.endDate).sort().at(-1) ?? '',
  );
  const today = formatLocalIsoDate(now);
  const [selectedDate, setSelectedDate] = useState(today);
  const datePages = getDatePages(allDates);
  const pageIndex = getDatePageIndex(allDates, selectedDate);
  const dates = datePages[pageIndex] ?? [];
  const hasPreviousPage = pageIndex > 0;
  const hasNextPage = pageIndex < datePages.length - 1;
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
      .map((record) => `${record.date}:${record.slot}`),
  );
  const gridTemplateColumns = `max-content repeat(${dates.length}, var(--spacing-touch))`;

  return (
    <section aria-label="복약 기록">
      <Card className="overflow-hidden p-4">
        <div className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-xl font-bold text-foreground">복약 기록</h2>
            <nav aria-label="복약 기록 기간 이동" className="flex items-center gap-1">
              <button
                type="button"
                aria-label="이전 10일"
                disabled={!hasPreviousPage}
                className="flex size-touch shrink-0 items-center justify-center rounded-control text-muted-foreground transition-colors hover:bg-muted-bg disabled:text-disabled-foreground disabled:hover:bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => {
                  const previousDate = datePages[pageIndex - 1]?.[0];
                  if (previousDate) setSelectedDate(previousDate);
                }}
              >
                <ChevronLeft aria-hidden className="size-5" />
              </button>
              <p
                aria-live="polite"
                className="min-w-28 text-center text-sm text-muted-foreground tnum"
              >
                {formatDatePeriod(dates[0] ?? '', dates.at(-1) ?? '')}
              </p>
              <button
                type="button"
                aria-label="다음 10일"
                disabled={!hasNextPage}
                className="flex size-touch shrink-0 items-center justify-center rounded-control text-muted-foreground transition-colors hover:bg-muted-bg disabled:text-disabled-foreground disabled:hover:bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => {
                  const nextDate = datePages[pageIndex + 1]?.[0];
                  if (nextDate) setSelectedDate(nextDate);
                }}
              >
                <ChevronRight aria-hidden className="size-5" />
              </button>
            </nav>
          </div>

          <div
            data-record-grid-scroll
            role="group"
            aria-label="복약 기록 가로 스크롤"
            tabIndex={0}
            className="min-w-0 overflow-x-auto overscroll-x-contain"
          >
            <div
              role="grid"
              aria-label="복약 기간 기록"
              className="grid w-max min-w-full gap-x-record-gap gap-y-0"
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
                          className="flex size-touch min-w-0 items-center justify-center justify-self-center rounded-record-cell bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          onClick={() => onMarkTaken(date, slot, recordIds)}
                        >
                          <span
                            aria-hidden
                            data-record-cell-visual
                            className="block aspect-square h-record-cell-h rounded-record-cell bg-border"
                          />
                        </button>
                      );
                    }

                    return (
                      <span
                        key={date}
                        role="gridcell"
                        aria-label={label}
                        className={`h-record-cell-h w-record-cell-w min-w-0 self-center justify-self-center rounded-record-cell ${CELL_CLASS[state]} ${
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
  const allTaken = takenRecords.has(`${date}:${slot}`);
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

function getDatePages(dates: string[]): string[][] {
  const pages: string[][] = [];
  for (let index = 0; index < dates.length; index += DAYS_PER_PAGE) {
    pages.push(dates.slice(index, index + DAYS_PER_PAGE));
  }
  return pages;
}

function getDatePageIndex(dates: string[], selectedDate: string): number {
  if (dates.length === 0) return 0;
  const selectedIndex = dates.findIndex((date) => date >= selectedDate);
  const nearestIndex = selectedIndex === -1 ? dates.length - 1 : selectedIndex;
  return Math.floor(nearestIndex / DAYS_PER_PAGE);
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
