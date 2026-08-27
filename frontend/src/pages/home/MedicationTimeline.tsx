import { useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import type {
  DoseRecord,
  MealSlot,
  MedicationOverview,
  MedicationOverviewItem,
} from '@/entities/medication';
import { mealSlotLabel, SLOT_ORDER } from '@/shared/model/mealSlot';
import { Button } from '@/shared/ui';

type TimelineStatus = 'completed' | 'current' | 'next' | 'missed';

interface TimelineMedication extends MedicationOverviewItem {
  recordId: number;
  startDate: string;
}

interface TimelineItemData {
  slot: MealSlot;
  label: string;
  time: string;
  medications: TimelineMedication[];
  recordIds: number[];
  status: TimelineStatus;
}

interface MedicationTimelineProps {
  overviews: MedicationOverview[];
  doseRecords: DoseRecord[];
  currentDate: string;
  onDoseChange: (recordIds: number[], slot: MealSlot, taken: boolean) => void;
}

export function MedicationTimeline({
  overviews,
  doseRecords,
  currentDate,
  onDoseChange,
}: MedicationTimelineProps) {
  const timeline = buildMedicationTimeline(overviews, new Date(), currentDate, doseRecords);
  const allTaken = timeline.length > 0 && timeline.every((item) => item.status === 'completed');

  return (
    <section className="flex flex-col gap-3" aria-labelledby="today-medication-title">
      <div className="flex items-center justify-between gap-3">
        <h2 id="today-medication-title" className="text-xl font-bold text-foreground">
          오늘의 복약
        </h2>
        <span className="text-sm text-muted-foreground tnum">
          {overviews.length > 1
            ? `${overviews.length}개 처방`
            : formatSingleEpisodeProgress(overviews[0], currentDate)}
        </span>
      </div>
      <div
        role="group"
        aria-label="하루 복약 시간표"
        className="overflow-hidden rounded-card bg-card shadow-card"
      >
        {allTaken && (
          <p className="border-b border-border px-4 py-3 text-base font-bold text-foreground">
            오늘 다 드셨어요
          </p>
        )}
        {timeline.map((item, index) => (
          <TimelineItem
            key={item.slot}
            item={item}
            divided={index > 0}
            onDoseChange={onDoseChange}
          />
        ))}
      </div>
    </section>
  );
}

function TimelineItem({
  item,
  divided,
  onDoseChange,
}: {
  item: TimelineItemData;
  divided: boolean;
  onDoseChange: MedicationTimelineProps['onDoseChange'];
}) {
  const [expanded, setExpanded] = useState(false);
  const current = item.status === 'current';
  const completed = item.status === 'completed';
  const statusLabel = completed
    ? '완료'
    : current
      ? '지금'
      : item.status === 'next'
        ? '다음'
        : null;

  return (
    <div className={divided ? 'border-t border-border' : ''}>
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={`timeline-detail-${item.slot}`}
        aria-label={`${item.label}약 ${item.medications.length}개 ${item.time} ${
          expanded ? '간단히 보기' : '자세히 보기'
        }`}
        className={`flex min-h-touch w-full items-center gap-3 px-4 py-3 text-left ${
          item.status === 'missed' ? 'text-muted-foreground' : 'text-foreground'
        }`}
        onClick={() => setExpanded((value) => !value)}
      >
        <span
          className={`flex size-5.5 shrink-0 items-center justify-center rounded-pill ${
            completed
              ? 'bg-primary text-card'
              : current
                ? 'border-2 border-primary'
                : 'border border-border'
          }`}
        >
          {completed && <Check aria-hidden className="size-4" />}
        </span>
        <span className="font-bold">
          {item.label}약 {item.medications.length}개
        </span>
        <span className="text-sm text-muted-foreground tnum">{item.time}</span>
        {statusLabel && (
          <span
            className={`ml-auto rounded-pill px-2.5 py-1 text-sm font-bold ${
              current
                ? 'bg-primary text-card'
                : 'bg-muted-bg text-muted-foreground'
            }`}
          >
            {statusLabel}
          </span>
        )}
        <ChevronDown
          aria-hidden
          className={`size-5 shrink-0 text-disabled-foreground transition-transform motion-reduce:transition-none ${
            expanded ? 'rotate-180' : ''
          } ${statusLabel ? '' : 'ml-auto'}`}
        />
      </button>

      {expanded && (
        <div
          id={`timeline-detail-${item.slot}`}
          role="group"
          aria-label={`${item.label}약 상세`}
          className={`border-t border-border px-4 py-4 ${current ? 'bg-primary-bg' : 'bg-card'}`}
        >
          <ul className="flex flex-col gap-3" aria-label={`${item.label}에 먹을 약`}>
            {item.medications.map((medication) => (
              <li
                key={`${medication.recordId}:${medication.medicationId}`}
                className="flex items-start justify-between gap-3"
              >
                <span className="text-base font-bold text-foreground">
                  {medication.name}{' '}
                  <span className="font-normal text-muted-foreground">{medication.dose}</span>
                </span>
                <span className="shrink-0 text-sm text-muted-foreground">
                  {formatPrescriptionLabel(medication.startDate)}
                </span>
              </li>
            ))}
          </ul>
          {item.status !== 'missed' && (
            <Button
              variant={current && !completed ? 'primary' : 'secondary'}
              className="mt-4"
              onClick={() => onDoseChange(item.recordIds, item.slot, !completed)}
            >
              <Check aria-hidden className="size-5" />
              {completed ? '복약 기록 되돌리기' : `${item.medications.length}개 먹었어요`}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function buildMedicationTimeline(
  overviews: MedicationOverview[],
  now: Date,
  currentDate: string,
  doseRecords: DoseRecord[],
): TimelineItemData[] {
  const medications = overviews.flatMap((overview) => {
    const todayOffset = daysBetween(overview.start.date, currentDate);
    return overview.medications
      .filter(
        (medication) =>
          !medication.asNeeded && todayOffset >= 0 && todayOffset < medication.days,
      )
      .map((medication) => ({
        ...medication,
        recordId: overview.recordId,
        startDate: overview.start.date,
      }));
  });
  const firstOverview = overviews[0];
  if (!firstOverview) return [];

  const items = SLOT_ORDER.map((slot) => {
    const slotMedications = medications.filter((medication) => medication.slots.includes(slot));
    return {
      slot,
      label: mealSlotLabel(slot, 'short'),
      time: firstOverview.mealTimes[slot],
      medications: slotMedications,
      recordIds: [...new Set(slotMedications.map((medication) => medication.recordId))],
    };
  })
    .filter((item) => item.medications.length > 0)
    .sort((left, right) => timeInMinutes(left.time) - timeInMinutes(right.time));

  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  let currentIndex = -1;
  items.forEach((item, index) => {
    if (timeInMinutes(item.time) <= nowMinutes) currentIndex = index;
  });

  return items.map((item, index) => {
    const completed = item.recordIds.every((recordId) =>
      doseRecords.some(
        (record) =>
          record.recordId === recordId &&
          record.date === currentDate &&
          record.slot === item.slot &&
          record.taken,
      ),
    );
    return {
      ...item,
      status: completed
        ? 'completed'
        : index === currentIndex
          ? 'current'
          : index < currentIndex
            ? 'missed'
            : 'next',
    };
  });
}

function formatSingleEpisodeProgress(
  overview: MedicationOverview | undefined,
  currentDate: string,
): string {
  if (!overview) return '';
  const dayNumber = Math.max(1, daysBetween(overview.start.date, currentDate) + 1);
  return `${dayNumber}일째 · ${overview.daysRemaining}일 남음`;
}

function formatPrescriptionLabel(value: string): string {
  const [, month, day] = value.split('-');
  return month && day ? `${Number(month)}월 ${Number(day)}일 처방` : '등록한 처방';
}

function timeInMinutes(value: string): number {
  const [hours = '0', minutes = '0'] = value.split(':');
  return Number(hours) * 60 + Number(minutes);
}

function daysBetween(from: string, to: string): number {
  const fromDate = localDate(from);
  const toDate = localDate(to);
  return Math.round((toDate.getTime() - fromDate.getTime()) / 86_400_000);
}

function localDate(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}
