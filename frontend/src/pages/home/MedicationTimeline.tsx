import { useEffect, useState } from 'react';
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
  alias?: string;
  medications: TimelineMedication[];
}

interface TimelineItemData {
  slot: MealSlot;
  label: string;
  time: string;
  medications: TimelineMedication[];
  episodes: TimelineEpisode[];
  completedEpisodeRecordIds: number[];
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
  const [expandedMedicationEpisodes, setExpandedMedicationEpisodes] = useState<Set<number>>(
    () => new Set(),
  );
  const [showAllEpisodes, setShowAllEpisodes] = useState(false);
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(() => new Set());
  const current = item.status === 'current';
  const [completedEpisodes, setCompletedEpisodes] = useState<Set<number>>(() =>
    new Set(item.completedEpisodeRecordIds),
  );
  const episodeFingerprint = [
    item.slot,
    item.time,
    ...item.episodes.map((episode) =>
      [
        episode.recordId,
        episode.startDate,
        episode.alias ?? '',
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
  const completionFingerprint = item.completedEpisodeRecordIds.join(',');
  useEffect(() => {
    setExpandedEpisodes(new Set());
    setExpandedMedicationEpisodes(new Set());
    setShowAllEpisodes(false);
    setSelectedEpisodes(new Set());
    setCompletedEpisodes(new Set(item.completedEpisodeRecordIds));
  }, [currentDate, episodeFingerprint]);

  useEffect(() => {
    setCompletedEpisodes(new Set(item.completedEpisodeRecordIds));
  }, [completionFingerprint]);

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

  function toggleMedicationList(recordId: number) {
    setExpandedMedicationEpisodes((currentEpisodes) => {
      const next = new Set(currentEpisodes);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  }

  function toggleAllEpisodes() {
    const nextShowAllEpisodes = !showAllEpisodes;
    setShowAllEpisodes(nextShowAllEpisodes);
    if (!nextShowAllEpisodes) {
      const visibleRecordIds = new Set(
        item.episodes.slice(0, 2).map((episode) => episode.recordId),
      );
      setSelectedEpisodes((currentEpisodes) =>
        new Set([...currentEpisodes].filter((recordId) => visibleRecordIds.has(recordId))),
      );
    }
  }

  const visibleEpisodes = showAllEpisodes ? item.episodes : item.episodes.slice(0, 2);
  const selected = visibleEpisodes.filter((episode) => selectedEpisodes.has(episode.recordId));
  const actionEpisodes = selected.length > 0 ? selected : visibleEpisodes;
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
      <div className="flex flex-col">
        {visibleEpisodes.map((episode) => {
          const episodeDate = formatDateLabel(episode.startDate);
          const episodeAlias = episode.alias?.trim();
          const episodeAccessibleName = `${episodeDate} 처방`;
          const episodeExpanded = expandedEpisodes.has(episode.recordId);
          const medicationsExpanded = expandedMedicationEpisodes.has(episode.recordId);
          const episodeCompleted = completedEpisodes.has(episode.recordId);
          const summary = episode.medications[0];
          const hiddenMedicationCount = Math.max(0, episode.medications.length - 3);
          const visibleMedications = medicationsExpanded
            ? episode.medications
            : episode.medications.slice(0, 3);
          const episodeTitle = episodeAlias || `${episodeDate} 처방`;

          return (
            <article
              key={episode.recordId}
              aria-label={`${episodeAccessibleName} · 약 ${episode.medications.length}개`}
              className="relative"
            >
              <button
                type="button"
                data-episode-row
                aria-pressed={selectedEpisodes.has(episode.recordId)}
                aria-label={`${episodeAccessibleName} ${episodeCompleted ? '복용 완료' : '선택'}`}
                className={`flex h-14 min-h-14 w-full items-center gap-3 border-b border-border px-3 py-1 pr-14 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${
                  selectedEpisodes.has(episode.recordId) ? 'bg-action-soft' : 'bg-card'
                }`}
                onClick={() => toggleSelectedEpisode(episode.recordId)}
              >
                <span
                  data-episode-selection-glyph
                  aria-hidden
                  className={`flex size-6 shrink-0 items-center justify-center rounded-pill ${
                    selectedEpisodes.has(episode.recordId) || episodeCompleted
                      ? 'bg-primary text-card'
                      : 'border-2 border-primary text-transparent'
                  }`}
                >
                  <Check className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex min-w-0 items-center gap-2">
                    <h3 className="truncate text-base font-bold text-foreground">{episodeTitle}</h3>
                    {episodeCompleted && (
                      <span
                        data-episode-completed-badge
                        className="inline-flex shrink-0 items-center gap-1 rounded-pill bg-primary-bg px-2 py-0.5 text-xs font-bold text-primary-strong"
                      >
                        복용 완료
                        <Check aria-hidden className="size-5" />
                      </span>
                    )}
                  </span>
                  <span className="block truncate text-sm text-muted-foreground">
                    {summary?.name ?? '복약'}
                    {episode.medications.length > 1
                      ? ` 외 ${episode.medications.length - 1}개`
                      : ''}
                  </span>
                </span>
              </button>

              <button
                type="button"
                aria-expanded={episodeExpanded}
                aria-controls={`episode-detail-${item.slot}-${episode.recordId}`}
                aria-label={`${episodeAccessibleName} ${episodeExpanded ? '접기' : '펼치기'}`}
                className="absolute right-1 top-1/2 flex size-touch -translate-y-1/2 items-center justify-center rounded-control text-primary-strong hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={(event) => {
                  event.stopPropagation();
                  toggleEpisode(episode.recordId);
                }}
              >
                <ChevronDown
                  aria-hidden
                  className={`size-5 transition-transform motion-reduce:transition-none ${
                    episodeExpanded ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {episodeExpanded && (
                <div
                  id={`episode-detail-${item.slot}-${episode.recordId}`}
                  role="group"
                  aria-label={`${episodeDate} 처방 약 상세`}
                  className="border-b border-border px-3 py-3"
                >
                  <ul className="flex flex-col gap-2" aria-label={`${episodeDate} 처방 약 목록`}>
                    {visibleMedications.map((medication) => (
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
                  {hiddenMedicationCount > 0 && (
                    <button
                      type="button"
                      aria-expanded={medicationsExpanded}
                      aria-label={
                        medicationsExpanded ? '약 목록 접기' : `약 ${hiddenMedicationCount}개 더보기`
                      }
                      className="mt-2 flex min-h-touch w-full items-center justify-end px-1 text-micro font-medium text-primary-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => toggleMedicationList(episode.recordId)}
                    >
                      {medicationsExpanded ? '접기' : `약 ${hiddenMedicationCount}개 더보기`}
                    </button>
                  )}
                </div>
              )}
            </article>
          );
        })}
        {item.episodes.length > 2 && (
          <button
            type="button"
            aria-expanded={showAllEpisodes}
            aria-label={showAllEpisodes ? '다른 처방 접기' : '다른 처방 펼치기'}
            className="flex min-h-touch items-center justify-end px-1 text-micro font-medium text-primary-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={toggleAllEpisodes}
          >
            {showAllEpisodes ? '다른 처방 접기' : '다른 처방 펼치기'}
          </button>
        )}
      </div>

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className="min-h-touch flex-1 rounded-button border border-border bg-card px-3 text-sm font-bold text-foreground hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={onMemo}
        >
          복약 메모
        </button>
        <Button
          fullWidth={false}
          variant={current && !actionCompleted ? 'primary' : 'secondary'}
          className="min-h-touch flex-1 px-3"
          onClick={handleDoseAction}
        >
          {actionCompleted ? '복약 기록 되돌리기' : '먹었어요'}
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
        alias: overview.alias,
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
    const completedEpisodeRecordIds = item.episodes
      .filter((episode) =>
        doseRecords.some(
          (record) =>
            record.date === currentDate &&
            record.slot === item.slot &&
            record.recordId === episode.recordId &&
            record.taken,
        ),
      )
      .map((episode) => episode.recordId);
    const completed =
      item.episodes.length > 0 &&
      item.episodes.every((episode) => completedEpisodeRecordIds.includes(episode.recordId));
    return {
      ...item,
      completedEpisodeRecordIds,
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
