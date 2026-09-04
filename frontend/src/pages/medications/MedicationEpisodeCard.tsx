import { ChevronDown, Clock3 } from 'lucide-react';
import type { MedicationOverview, MedicationOverviewItem } from '@/entities/medication';
import { formatDateLabel, formatDatePeriod } from '@/shared/lib/dateLabel';
import { mealSlotLabel } from '@/shared/model/mealSlot';
import { Checkbox } from '@/shared/ui';

interface MedicationEpisodeCardProps {
  overview: MedicationOverview;
  expanded: boolean;
  selectionMode: boolean;
  selected: boolean;
  onToggleExpanded: () => void;
  onToggleSelected: () => void;
  onEditMedication: (medication: MedicationOverviewItem) => void;
  /** Feature #252 본 경로에서는 회차 전체를 바로 편집/열람합니다. */
  feature252?: boolean;
  onOpenEpisode?: () => void;
}

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

  return (
    <article className="overflow-hidden rounded-card bg-card shadow-card">
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
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          aria-label={`${dateLabel} 처방 · 약 ${overview.medications.length}개 · ${statusLabel}`}
          className="flex min-h-24 min-w-0 flex-1 items-center gap-3 p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
          onClick={selectionMode ? onToggleSelected : (onOpenEpisode ?? onToggleExpanded)}
        >
          <span className="min-w-0 flex-1">
            <strong className="block text-lg text-foreground">
              {feature252 && overview.alias ? overview.alias : `${dateLabel} 처방`}
            </strong>
            <span className="mt-1 block text-sm text-muted-foreground tnum">
              {formatDatePeriod(overview.start.date, overview.endDate, { includeYear: true })} · 약{' '}
              {overview.medications.length}개
            </span>
          </span>
          <span className="flex shrink-0 flex-col items-end gap-1">
            <span
              className={`rounded-pill px-3 py-1.5 text-sm font-bold ${
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
          <ChevronDown
            aria-hidden
            className={`size-5 shrink-0 text-disabled-foreground transition-transform motion-reduce:transition-none ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        </button>
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
              <li key={medication.medicationId} className="flex items-start gap-3 py-4">
                <div className="min-w-0 flex-1">
                  <p className="font-bold text-foreground">
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
                          className="rounded-pill bg-muted-bg px-3 py-1 text-sm text-muted-foreground"
                        >
                          {mealSlotLabel(slot)}
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
                {!overview.isFinished && !medication.asNeeded && (
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
