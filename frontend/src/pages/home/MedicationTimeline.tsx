import { useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import type {
  DoseRecord,
  MealSlot,
  MedicationOverview,
  MedicationOverviewItem,
} from '@/entities/medication';
import { formatDateLabel } from '@/shared/lib/dateLabel';
import { mealSlotLabel, SLOT_ORDER } from '@/shared/model/mealSlot';
import { Button } from '@/shared/ui';

type TimelineStatus = 'completed' | 'current' | 'next' | 'missed';

interface TimelineMedication extends MedicationOverviewItem {
  recordId: number;
  startDate: string;
}

interface TimelineEpisode {
  recordId: number;
  startDate: string;
  medications: TimelineMedication[];
}

interface TimelineItemData {
  slot: MealSlot;
  label: string;
  time: string;
  medications: TimelineMedication[];
  episodes: TimelineEpisode[];
  recordIds: number[];
  status: TimelineStatus;
}

interface MedicationTimelineProps {
  overviews: MedicationOverview[];
  doseRecords: DoseRecord[];
  currentDate: string;
  onDoseChange: (recordIds: number[], slot: MealSlot, taken: boolean) => void;
  onMemo: () => void;
}

export function MedicationTimeline({
  overviews,
  doseRecords,
  currentDate,
  onDoseChange,
  onMemo,
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
            onMemo={onMemo}
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
  onMemo,
}: {
  item: TimelineItemData;
  divided: boolean;
  onDoseChange: MedicationTimelineProps['onDoseChange'];
  onMemo: MedicationTimelineProps['onMemo'];
}) {
  const [expanded, setExpanded] = useState(false);
  const [expandedEpisodes, setExpandedEpisodes] = useState<Set<number>>(() => new Set());
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(() => new Set());
  const [completedEpisodes, setCompletedEpisodes] = useState<Set<number>>(() => new Set());
  const current = item.status === 'current';
  const completed = item.status === 'completed';
  const statusLabel = completed
    ? '완료'
    : current
      ? '지금'
      : item.status === 'next'
        ? '다음'
        : null;

  function toggleEpisode(recordId: number) {
    setExpandedEpisodes((currentEpisodes) => {
      const next = new Set(currentEpisodes);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  }

  function toggleSelectedEpisode(recordId: number) {
    setSelectedEpisodes((currentEpisodes) => {
      const next = new Set(currentEpisodes);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  }

  const selected = item.episodes.filter((episode) => selectedEpisodes.has(episode.recordId));
  const actionEpisodes = selected.length > 0 ? selected : item.episodes;
  const actionMedicationCount = actionEpisodes.reduce(
    (count, episode) => count + episode.medications.length,
    0,
  );
  const actionRecordIds = actionEpisodes.map((episode) => episode.recordId);

  function handleDoseAction() {
    setCompletedEpisodes((currentEpisodes) => {
      if (completed) return new Set();
      return new Set([...currentEpisodes, ...actionRecordIds]);
    });
    setSelectedEpisodes(new Set());
    onDoseChange(actionRecordIds, item.slot, !completed);
  }

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
              current ? 'bg-primary text-card' : 'bg-muted-bg text-muted-foreground'
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
          <div className="flex flex-col gap-3">
            {item.episodes.map((episode) => {
              const episodeDate = formatDateLabel(episode.startDate);
              const episodeExpanded = expandedEpisodes.has(episode.recordId);
              const episodeCompleted =
                completedEpisodes.size === 0 ? completed : completedEpisodes.has(episode.recordId);
              const summary = episode.medications[0];
              const remainingCount = Math.max(0, episode.medications.length - 1);

              return (
                <article
                  key={episode.recordId}
                  aria-label={`${episodeDate} 처방 · 약 ${episode.medications.length}개`}
                  className={`rounded-button p-3 ${
                    completed ? 'bg-primary-bg' : 'bg-muted-bg'
                  }`}
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="text-base font-bold text-foreground">{episodeDate} 처방</h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {summary?.name ?? '복약'}
                        {remainingCount > 0 ? ` 외 ${remainingCount}개` : ''}
                      </p>
                      <p className="mt-1 truncate text-sm text-muted-foreground">
                        {episode.medications.map(formatMedication).join(' · ')}
                      </p>
                      {episode.medications.length > 1 && (
                        <span className="mt-1 block text-xs text-disabled-foreground">
                          {episodeDate} 처방
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      aria-pressed={selectedEpisodes.has(episode.recordId)}
                      aria-label={`${episodeDate} 처방 ${episodeCompleted ? '복용 완료' : '선택'}`}
                      className={`flex min-h-touch min-w-touch shrink-0 items-center justify-center rounded-pill focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        selectedEpisodes.has(episode.recordId) || episodeCompleted
                          ? 'bg-primary text-card'
                          : 'border-2 border-primary text-transparent'
                      }`}
                      onClick={() => toggleSelectedEpisode(episode.recordId)}
                    >
                      <Check aria-hidden className="size-4" />
                    </button>
                  </div>

                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      aria-expanded={episodeExpanded}
                      aria-controls={`episode-detail-${item.slot}-${episode.recordId}`}
                      aria-label={`${episodeDate} 처방 ${episodeExpanded ? '접기' : '펼치기'}`}
                      className="min-h-touch rounded-control px-3 text-sm font-bold text-primary-strong hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => toggleEpisode(episode.recordId)}
                    >
                      {episodeExpanded ? '접기' : '펼치기'}
                      <ChevronDown
                        aria-hidden
                        className={`ml-1 inline-block size-4 transition-transform motion-reduce:transition-none ${
                          episodeExpanded ? 'rotate-180' : ''
                        }`}
                      />
                    </button>
                  </div>

                  {episodeExpanded && (
                    <div
                      id={`episode-detail-${item.slot}-${episode.recordId}`}
                      role="group"
                      aria-label={`${episodeDate} 처방 약 상세`}
                      className="mt-2 border-t border-border pt-3"
                    >
                      <ul className="flex flex-col gap-2" aria-label={`${episodeDate} 처방 약 목록`}>
                        {episode.medications.map((medication) => (
                          <li
                            key={`${medication.recordId}:${medication.medicationId}`}
                            className="flex items-start justify-between gap-3"
                          >
                            <span className="text-base font-bold text-foreground">
                              {medication.name}{' '}
                              <span className="font-normal text-muted-foreground">
                                {medication.dose}
                              </span>
                            </span>
                            <span className="shrink-0 text-sm text-muted-foreground">
                              {formatPrescriptionLabel(medication.startDate)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </article>
              );
            })}
          </div>

          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className="min-h-touch flex-1 rounded-button border border-border bg-card px-3 text-sm font-bold text-foreground hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={onMemo}
            >
              복약 메모 쓰기
            </button>
            <Button
              fullWidth={false}
              variant={current && !completed ? 'primary' : 'secondary'}
              className="min-h-touch flex-1 px-3"
              onClick={handleDoseAction}
            >
              <Check aria-hidden className="size-5" />
              {completed ? '복약 기록 되돌리기' : `${actionMedicationCount}개 먹었어요`}
            </Button>
          </div>
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
    const episodes = overviews
      .map((overview) => ({
        recordId: overview.recordId,
        startDate: overview.start.date,
        medications: slotMedications.filter(
          (medication) => medication.recordId === overview.recordId,
        ),
      }))
      .filter((episode) => episode.medications.length > 0)
      .sort((left, right) => left.startDate.localeCompare(right.startDate));

    return {
      slot,
      label: mealSlotLabel(slot, 'short'),
      time: firstOverview.mealTimes[slot],
      medications: slotMedications,
      episodes,
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
    const completed = doseRecords.some(
      (record) =>
        record.date === currentDate &&
        record.slot === item.slot &&
        record.taken,
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

function formatMedication(medication: TimelineMedication): string {
  return `${medication.name} ${medication.dose}`;
}

function formatPrescriptionLabel(value: string): string {
  const label = formatDateLabel(value);
  return label === value ? '등록한 처방' : `${label} 처방`;
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
