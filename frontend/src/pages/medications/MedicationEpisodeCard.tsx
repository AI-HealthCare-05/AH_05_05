import { ChevronDown, Clock3, Pencil } from 'lucide-react';
import type { MedicationOverview, MedicationOverviewItem } from '@/entities/medication';
import { formatDateLabel, formatDatePeriod } from '@/shared/lib/dateLabel';
import { SLOT_ORDER, mealSlotLabel, type MealSlot } from '@/shared/model/mealSlot';
import { Checkbox } from '@/shared/ui';

interface MedicationEpisodeCardProps {
  overview: MedicationOverview;
  expanded: boolean;
  selectionMode: boolean;
  selected: boolean;
  onToggleExpanded: () => void;
  onToggleSelected: () => void;
  onEditMedication: (medication: MedicationOverviewItem) => void;
  /** 본 경로에서는 요약을 펼치고 연필로 회차 전체를 편집합니다. */
  feature252?: boolean;
  onOpenEpisode?: () => void;
}

const SLOT_CHIP_CLASSES: Record<MealSlot, string> = {
  morning: 'bg-warning-bg text-warning-strong',
  lunch: 'bg-primary-bg text-primary-strong',
  evening: 'bg-warm-200 text-brand',
  bedtime: 'bg-muted-bg text-muted-foreground',
};

export function MedicationEpisodeCard({
  overview,
  expanded,
  selectionMode,
  selected,
  onToggleExpanded,
  onToggleSelected,
  onEditMedication,
  feature252 = false,
  onOpenEpisode,
}: MedicationEpisodeCardProps) {
  const dateLabel = formatDateLabel(overview.start.date, { includeYear: true });
  const panelId = `medication-episode-${overview.recordId}`;
  const statusLabel = overview.isFinished ? '복용 완료' : '복용 중';
  const dDay = overview.daysRemaining <= 1 ? 'D-Day' : `D-${overview.daysRemaining - 1}`;
  const scheduledSlots = SLOT_ORDER.filter((slot) =>
    overview.medications.some((medication) => !medication.asNeeded && medication.slots.includes(slot)),
  );

  return (
    <article className="rounded-card bg-card shadow-card">
      <div className="flex min-w-0 items-stretch">
        {selectionMode && (
          <label className="flex min-h-touch shrink-0 cursor-pointer items-center pl-4">
            <Checkbox
              checked={selected}
              aria-label={`${dateLabel} 처방 선택`}
              onCheckedChange={onToggleSelected}
            />
          </label>
        )}
        <div className="min-w-0 flex-1">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={panelId}
            aria-label={`${dateLabel} 처방 · 약 ${overview.medications.length}개 · ${statusLabel}`}
            className={`flex min-h-24 w-full min-w-0 items-center gap-3 p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${feature252 ? 'pb-0' : ''}`}
            onClick={selectionMode ? onToggleSelected : onToggleExpanded}
          >
            <span className="min-w-0 flex-1">
              <span className="mb-2 flex min-w-0 flex-wrap items-center gap-2">
                <span
                  className={`shrink-0 rounded-pill px-2.5 py-1 text-xs font-bold ${
                    overview.isFinished
                      ? 'bg-muted-bg text-muted-foreground'
                      : 'bg-primary-bg text-primary-strong'
                  }`}
                >
                  {statusLabel}
                </span>
                {!overview.isFinished && (
                  <span className="text-xs font-bold text-primary-strong tnum">
                    {feature252 ? `${Math.max(0, overview.daysRemaining)}일 남음` : dDay}
                  </span>
                )}
              </span>
              <strong className="block [overflow-wrap:anywhere] text-lg text-foreground">
                {feature252 && overview.alias?.trim() ? overview.alias : `${dateLabel} 처방`}
              </strong>
              <span className="mt-1 block whitespace-normal [overflow-wrap:anywhere] text-sm text-muted-foreground tnum">
                {formatDatePeriod(overview.start.date, overview.endDate, { includeYear: true })}
                {!feature252 && ` · 약 ${overview.medications.length}개`}
              </span>
            </span>
            <ChevronDown
              aria-hidden
              className={`size-5 shrink-0 text-disabled-foreground transition-transform motion-reduce:transition-none ${
                expanded ? 'rotate-180' : ''
              }`}
            />
          </button>
          {feature252 && (
            <div className="mt-3 flex min-w-0 items-start gap-2 px-4 pb-3">
              <div className="flex min-h-touch min-w-0 flex-1 flex-wrap content-start gap-2 py-2">
                {scheduledSlots.map((slot) => (
                  <span key={slot} className={`rounded-pill px-2.5 py-1 text-xs font-bold ${SLOT_CHIP_CLASSES[slot]}`}>
                    {mealSlotLabel(slot)}
                  </span>
                ))}
              </div>
              {!selectionMode && !overview.isFinished && onOpenEpisode && (
                <button
                  type="button"
                  aria-label={`처방 수정 · ${dateLabel}`}
                  className="flex min-h-touch min-w-touch shrink-0 items-center justify-center rounded-control text-primary-strong hover:bg-primary-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={onOpenEpisode}
                >
                  <Pencil aria-hidden className="size-4" />
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {expanded && (
        <div
          id={panelId}
          role="region"
          aria-label={`${dateLabel} 처방 상세`}
          className="border-t border-border px-4 pb-4"
        >
          <ul className="divide-y divide-border" aria-label={`${dateLabel} 처방 약 목록`}>
            {overview.medications.map((medication) => (
              <li key={medication.medicationId} className="flex min-w-0 items-start gap-3 py-4">
                <div className="min-w-0 flex-1">
                  <p className="[overflow-wrap:anywhere] font-bold text-foreground">
                    {medication.name}{' '}
                    <span className="font-normal text-muted-foreground">{medication.dose}</span>
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {medication.asNeeded ? (
                      <span className="rounded-pill bg-muted-bg px-3 py-1 text-sm text-muted-foreground">
                        필요할 때만 · 알림 없음
                      </span>
                    ) : (
                      medication.slots.map((slot) => (
                        <span
                          key={slot}
                          className={`rounded-pill px-3 py-1 text-sm ${feature252 ? SLOT_CHIP_CLASSES[slot] : 'bg-muted-bg text-muted-foreground'}`}
                        >
                          {mealSlotLabel(slot)}
                          {feature252 && ` ${overview.mealTimes[slot]}`}
                        </span>
                      ))
                    )}
                    {medication.untilComplete && (
                      <span className="rounded-pill bg-warning-bg px-3 py-1 text-sm text-warning-strong">
                        끝까지 복용
                      </span>
                    )}
                  </div>
                </div>
                {!feature252 && !selectionMode && !overview.isFinished && !medication.asNeeded && (
                  <button
                    type="button"
                    aria-label={`${medication.name} ${medication.dose} 복용 시간 수정`}
                    className="flex min-h-touch shrink-0 items-center gap-1 rounded-control px-2 text-sm font-bold text-primary-strong hover:bg-primary-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => onEditMedication(medication)}
                  >
                    <Clock3 aria-hidden className="size-4" />
                    시간
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
