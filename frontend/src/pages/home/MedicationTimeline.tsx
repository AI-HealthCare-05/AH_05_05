import { useEffect, useRef, useState } from 'react';
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
  status: TimelineStatus;
}

interface MedicationTimelineProps {
  overviews: MedicationOverview[];
  doseRecords: DoseRecord[];
  currentDate: string;
  onDoseChange: (
    recordIds: number[],
    slot: MealSlot,
    taken: boolean,
  ) => void | Promise<boolean>;
  onMemo: () => void;
}

export function MedicationTimeline({
  overviews,
  doseRecords,
  currentDate,
  onDoseChange,
  onMemo,
}: MedicationTimelineProps) {
  const now = new Date();
  const timeline = buildMedicationTimeline(overviews, now, currentDate, doseRecords);
  const item = selectPrimaryTimelineItem(timeline, now);

  return (
    <section className="flex flex-col gap-3" aria-label="오늘의 복약">
      {item ? (
        <div className="overflow-hidden rounded-card bg-card shadow-card">
          <div className="flex items-center justify-between gap-3 px-4 pt-4">
            <p className="text-base font-bold text-foreground">
              {item.label} {item.time}
            </p>
            <span className="text-sm text-muted-foreground tnum">
              {item.episodes.length > 1
                ? `처방 ${item.episodes.length}개`
                : formatSingleEpisodeProgress(
                    overviews.find((overview) => overview.recordId === item.episodes[0]?.recordId),
                    currentDate,
                  )}
            </span>
          </div>
          <TimelineItem
            item={item}
            currentDate={currentDate}
            onDoseChange={onDoseChange}
            onMemo={onMemo}
          />
        </div>
      ) : (
        <div className="rounded-card bg-card p-4 text-sm text-muted-foreground shadow-card">
          오늘 복약할 약이 없어요.
        </div>
      )}
    </section>
  );
}

function TimelineItem({
  item,
  currentDate,
  onDoseChange,
  onMemo,
}: {
  item: TimelineItemData;
  currentDate: string;
  onDoseChange: MedicationTimelineProps['onDoseChange'];
  onMemo: MedicationTimelineProps['onMemo'];
}) {
  const [expandedEpisodes, setExpandedEpisodes] = useState<Set<number>>(() => new Set());
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(() => new Set());
  const current = item.status === 'current';
  const completed = item.status === 'completed';
  const [completedEpisodes, setCompletedEpisodes] = useState<Set<number>>(() =>
    completed ? new Set(item.episodes.map((episode) => episode.recordId)) : new Set(),
  );
  const previousCompleted = useRef(completed);
  const episodeFingerprint = [
    item.slot,
    item.time,
    ...item.episodes.map((episode) =>
      [
        episode.recordId,
        episode.startDate,
        ...episode.medications.map((medication) =>
          [
            medication.medicationId,
            medication.name,
            medication.dose,
            medication.days,
            medication.daysRemaining,
            medication.asNeeded,
            medication.slots.join(','),
          ].join(':'),
        ),
      ].join('|'),
    ),
  ].join('||');
  useEffect(() => {
    setExpandedEpisodes(new Set());
    setSelectedEpisodes(new Set());
    setCompletedEpisodes(
      completed ? new Set(item.episodes.map((episode) => episode.recordId)) : new Set(),
    );
  }, [currentDate, episodeFingerprint]);

  useEffect(() => {
    if (previousCompleted.current && !completed) {
      setSelectedEpisodes(new Set());
      setCompletedEpisodes(new Set());
    }
    previousCompleted.current = completed;
  }, [completed]);

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
  const actionCompleted =
    actionEpisodes.length > 0 &&
    actionEpisodes.every((episode) => completedEpisodes.has(episode.recordId));

  async function handleDoseAction() {
    const previousCompletedEpisodes = completedEpisodes;
    const previousSelectedEpisodes = selectedEpisodes;
    setCompletedEpisodes((currentEpisodes) => {
      if (actionCompleted) {
        return new Set(
          [...currentEpisodes].filter((recordId) => !actionRecordIds.includes(recordId)),
        );
      }
      return new Set([...currentEpisodes, ...actionRecordIds]);
    });
    setSelectedEpisodes(new Set());
    let saved = true;
    try {
      saved = (await onDoseChange(actionRecordIds, item.slot, !actionCompleted)) !== false;
    } catch {
      saved = false;
    }
    if (saved === false) {
      setCompletedEpisodes(previousCompletedEpisodes);
      setSelectedEpisodes(previousSelectedEpisodes);
    }
  }

  return (
    <div role="group" aria-label={`${item.label}약 상세`} className="px-4 pb-4 pt-3">
      <div className="flex flex-col gap-3">
        {item.episodes.map((episode) => {
          const episodeDate = formatDateLabel(episode.startDate);
          const episodeExpanded = expandedEpisodes.has(episode.recordId);
          const episodeCompleted = completedEpisodes.has(episode.recordId);
          const summary = episode.medications[0];
          const remainingCount = Math.max(0, episode.medications.length - 1);

          return (
            <article
              key={episode.recordId}
              aria-label={`${episodeDate} 처방 · 약 ${episode.medications.length}개`}
              className={`rounded-button p-3 ${episodeCompleted ? 'bg-primary-bg' : 'bg-muted-bg'}`}
            >
              <div className="flex min-w-0 items-start gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="text-base font-bold text-foreground">{episodeDate} 처방</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {summary?.name ?? '복약'}
                    {remainingCount > 0 ? ` 외 ${remainingCount}개` : ''}
                  </p>
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
                  <p className="mb-3 text-sm text-muted-foreground">
                    {episode.medications.map(formatMedication).join(' · ')}
                  </p>
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
            variant={current && !actionCompleted ? 'primary' : 'secondary'}
            className="min-h-touch flex-1 px-3"
            onClick={handleDoseAction}
          >
            <Check aria-hidden className="size-5" />
            {actionCompleted ? '복약 기록 되돌리기' : `${actionMedicationCount}개 먹었어요`}
          </Button>
        </div>
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

function selectPrimaryTimelineItem(
  timeline: TimelineItemData[],
  now: Date,
): TimelineItemData | undefined {
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  return (
    timeline.filter((item) => timeInMinutes(item.time) <= nowMinutes).at(-1) ?? timeline[0]
  );
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
