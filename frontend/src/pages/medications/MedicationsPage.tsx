import { useEffect, useMemo, useRef, useState } from 'react';
import { Filter, Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { useSession } from '@/app/SessionContext';
import {
  cancelMedication,
  getMedicationOverviews,
  saveMedicationSchedule,
  type MealSlot,
  type MedicationOverview,
  type MedicationOverviewItem,
  type MedicationOverviewRange,
} from '@/entities/medication';
import { updateEpisodeAlias } from '@/entities/medication-alias';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';
import {
  BottomTabbar,
  Button,
  Card,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  ErrorDialog,
  Header,
  Input,
} from '@/shared/ui';
import { MEAL_SLOTS, SLOT_ORDER, mealSlotLabel } from '@/shared/model/mealSlot';
import { cn } from '@/shared/lib/cn';
import { formatDateLabel, formatDatePeriod } from '@/shared/lib/dateLabel';
import { MedicationBulkDeleteDialog } from './MedicationBulkDeleteDialog';
import { MedicationEpisodeCard } from './MedicationEpisodeCard';
import { MedicationPeriodFilterSheet } from './MedicationPeriodFilterSheet';
import { MedicationSlotSheet } from './MedicationSlotSheet';
import { medicationPeriodLabel, medicationRangeFromSearchParams } from './medicationPeriod';

interface MedicationsPageProps {
  overviewsLoader?: (range?: MedicationOverviewRange) => Promise<MedicationOverview[]>;
  medicationCanceller?: (recordId: number) => Promise<void>;
  /** 본 경로의 회차 단위 편집/읽기 전용 화면을 켭니다. */
  feature252?: boolean;
}

interface EditingMedication {
  recordId: number;
  medication: MedicationOverviewItem;
}

export function MedicationsPage({
  overviewsLoader = getMedicationOverviews,
  medicationCanceller = cancelMedication,
  feature252 = false,
}: MedicationsPageProps) {
  const navigate = useNavigate();
  const { principalKey } = useSession();
  const overviewRequestRef = useRef<{
    key: string;
    loader: typeof overviewsLoader;
    promise: Promise<MedicationOverview[]>;
  } | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const queryKey = searchParams.toString();
  const range = useMemo(
    () => medicationRangeFromSearchParams(new URLSearchParams(queryKey)),
    [queryKey],
  );
  const [overviews, setOverviews] = useState<MedicationOverview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [expandedRecordIds, setExpandedRecordIds] = useState<Set<number>>(new Set());
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedRecordIds, setSelectedRecordIds] = useState<Set<number>>(new Set());
  const [filterOpen, setFilterOpen] = useState(false);
  const [editing, setEditing] = useState<EditingMedication | null>(null);
  const [episodeEditing, setEpisodeEditing] = useState<MedicationOverview | null>(null);
  const [episodeAlias, setEpisodeAlias] = useState('');
  const [episodeSlots, setEpisodeSlots] = useState<Record<number, MealSlot[]>>({});
  const [episodeSaving, setEpisodeSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteTargets, setDeleteTargets] = useState<number[]>([]);

  useEffect(() => {
    let cancelled = false;
    const requestKey = `${principalKey ?? 'anonymous'}:${queryKey}:${reloadKey}`;
    if (
      overviewRequestRef.current?.key !== requestKey ||
      overviewRequestRef.current.loader !== overviewsLoader
    ) {
      overviewRequestRef.current = {
        key: requestKey,
        loader: overviewsLoader,
        promise: overviewsLoader(range),
      };
    }
    setExpandedRecordIds(new Set());
    setSelectionMode(false);
    setSelectedRecordIds(new Set());
    window.scrollTo(0, 0);
    setLoadError(null);
    setOverviews(null);
    overviewRequestRef.current.promise
      .then((data) => {
        if (cancelled) return;
        const next = data.filter((overview) => overview.medications.length > 0);
        const nextIds = new Set(next.map((overview) => overview.recordId));
        setOverviews(next);
        setExpandedRecordIds((current) => new Set([...current].filter((id) => nextIds.has(id))));
        setSelectedRecordIds((current) => new Set([...current].filter((id) => nextIds.has(id))));
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : '복용약을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [overviewsLoader, principalKey, queryKey, range, reloadKey]);

  function toggleExpanded(recordId: number) {
    setExpandedRecordIds((current) => {
      const next = new Set(current);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  }

  function toggleSelected(recordId: number) {
    setSelectedRecordIds((current) => {
      const next = new Set(current);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  }

  function openEpisode(overview: MedicationOverview) {
    setEpisodeEditing(overview);
    setEpisodeAlias(overview.alias ?? '');
    setEpisodeSlots(
      Object.fromEntries(
        overview.medications.map((medication) => [medication.medicationId, [...medication.slots]]),
      ),
    );
  }

  function toggleEpisodeSlot(medicationId: number, slot: MealSlot) {
    setEpisodeSlots((current) => {
      const next = new Set(current[medicationId] ?? []);
      if (next.has(slot)) next.delete(slot);
      else next.add(slot);
      return { ...current, [medicationId]: SLOT_ORDER.filter((value) => next.has(value)) };
    });
  }

  async function saveEpisode() {
    if (!episodeEditing || episodeSaving) return;
    setEpisodeSaving(true);
    setSaveError(null);
    try {
      await saveMedicationSchedule(episodeEditing.recordId, {
        start: episodeEditing.start,
        mealTimes: episodeEditing.mealTimes,
        medications: episodeEditing.medications
          .filter((medication) => !medication.asNeeded)
          .map((medication) => ({
            medicationId: medication.medicationId,
            slots: episodeSlots[medication.medicationId] ?? [],
          })),
      });
      await updateEpisodeAlias(episodeEditing.recordId, episodeAlias);
      setOverviews((current) =>
        current?.map((overview) =>
          overview.recordId === episodeEditing.recordId
            ? {
                ...overview,
                alias: episodeAlias.trim() || undefined,
                medications: overview.medications.map((medication) => ({
                  ...medication,
                  slots: episodeSlots[medication.medicationId] ?? medication.slots,
                })),
              }
            : overview,
        ) ?? null,
      );
      setEpisodeEditing(null);
      toast.success('처방을 저장했어요.');
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '처방을 저장하지 못했어요.');
    } finally {
      setEpisodeSaving(false);
    }
  }

  function leaveSelectionMode() {
    setSelectionMode(false);
    setSelectedRecordIds(new Set());
  }

  async function saveMedicationSlots(slots: MealSlot[]) {
    if (!editing || !overviews) return;
    const overview = overviews.find((item) => item.recordId === editing.recordId);
    if (!overview) return;
    setSaveError(null);
    const nextMedications = overview.medications.map((medication) =>
      medication.medicationId === editing.medication.medicationId
        ? { ...medication, slots }
        : medication,
    );
    try {
      await saveMedicationSchedule(overview.recordId, {
        start: overview.start,
        mealTimes: overview.mealTimes,
        medications: nextMedications
          .filter((medication) => !medication.asNeeded)
          .map((medication) => ({
            medicationId: medication.medicationId,
            slots: medication.slots,
          })),
      });
      setOverviews((current) =>
        current?.map((item) =>
          item.recordId === overview.recordId ? { ...item, medications: nextMedications } : item,
        ) ?? null,
      );
      setEditing(null);
      toast.success('복용 시간을 바꿨어요.');
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : '복용 시간을 저장하지 못했어요.');
    }
  }

  function openDeleteConfirmation() {
    if (!overviews) return;
    const targets = overviews
      .filter((overview) => selectedRecordIds.has(overview.recordId))
      .map((overview) => overview.recordId);
    if (targets.length === 0) return;
    setDeleteTargets(targets);
    setDeleteError(null);
    setDeleteOpen(true);
  }

  async function deleteSelectedMedications(recordIds: number[]) {
    if (deletePending || recordIds.length === 0) return;
    setDeletePending(true);
    setDeleteError(null);
    const succeeded: number[] = [];
    const failed: number[] = [];
    for (const recordId of recordIds) {
      try {
        await medicationCanceller(recordId);
        succeeded.push(recordId);
      } catch {
        failed.push(recordId);
      }
    }

    if (succeeded.length > 0) {
      const succeededIds = new Set(succeeded);
      setOverviews((current) => current?.filter((item) => !succeededIds.has(item.recordId)) ?? null);
      setExpandedRecordIds((current) => new Set([...current].filter((id) => !succeededIds.has(id))));
    }

    if (failed.length === 0) {
      setDeleteOpen(false);
      leaveSelectionMode();
      toast.success(`${succeeded.length}개를 삭제했어요`);
    } else if (succeeded.length > 0) {
      setDeleteOpen(false);
      setSelectedRecordIds(new Set(failed));
      setDeleteTargets(failed);
      toast.warning(`${succeeded.length}개를 삭제했어요. ${failed.length}개는 실패했어요`);
    } else {
      setSelectedRecordIds(new Set(failed));
      setDeleteTargets(failed);
      setDeleteError('선택한 복약 정보를 삭제하지 못했어요. 다시 시도해주세요.');
    }
    setDeletePending(false);
  }

  const headerTitle = selectionMode ? `${selectedRecordIds.size}개 선택` : '복약';
  const periodLabel = medicationPeriodLabel(range, new Date());
  const activeOverviews = overviews?.filter((overview) => !overview.isFinished) ?? [];
  const finishedOverviews = overviews?.filter((overview) => overview.isFinished) ?? [];

  function renderEpisodeCard(overview: MedicationOverview) {
    return (
      <MedicationEpisodeCard
        key={overview.recordId}
        overview={overview}
        expanded={expandedRecordIds.has(overview.recordId)}
        selectionMode={selectionMode}
        selected={selectedRecordIds.has(overview.recordId)}
        onToggleExpanded={() => toggleExpanded(overview.recordId)}
        onToggleSelected={() => toggleSelected(overview.recordId)}
        onEditMedication={(medication) =>
          setEditing({ recordId: overview.recordId, medication })
        }
        feature252={feature252}
        onOpenEpisode={feature252 ? () => openEpisode(overview) : undefined}
      />
    );
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header
        title={headerTitle}
        onBack={() => navigate(-1)}
        right={
          selectionMode ? (
            <div className="flex shrink-0 items-center gap-1">
              {selectedRecordIds.size > 0 && (
                <button
                  type="button"
                  className="min-h-touch px-2 text-sm font-bold text-danger-strong"
                  onClick={openDeleteConfirmation}
                >
                  삭제하기
                </button>
              )}
              <button
                type="button"
                className="min-h-touch px-2 text-sm font-bold text-muted-foreground"
                onClick={leaveSelectionMode}
              >
                취소
              </button>
            </div>
          ) : (
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                aria-label="새 약봉투 등록"
                className="flex size-touch items-center justify-center text-primary"
                onClick={() => navigate('/document-upload')}
              >
                <Plus aria-hidden className="size-6" />
              </button>
              <button
                type="button"
                className="min-h-touch px-2 text-sm font-bold text-muted-foreground"
                onClick={() => setSelectionMode(true)}
              >
                삭제
              </button>
            </div>
          )
        }
      />

      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="flex min-h-touch w-fit max-w-full items-center gap-2 rounded-pill border border-border bg-card px-4 text-sm font-bold text-foreground shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setFilterOpen(true)}
          >
            <Filter aria-hidden className="size-4 shrink-0 text-primary" />
            {periodLabel}
          </button>
          {feature252 && (
            <button
              type="button"
              className="min-h-touch rounded-pill border border-border bg-card px-4 text-sm font-bold text-foreground"
              onClick={() => navigate('/medications/notes')}
            >
              복약 메모
            </button>
          )}
        </div>

        {feature252 && (
          <Button
            fullWidth={false}
            className="self-start"
            onClick={() => navigate('/document-upload')}
          >
            <Plus aria-hidden className="mr-1 size-4" />
            처방 추가
          </Button>
        )}

        {loadError ? (
          <Card title="복용약을 불러오지 못했어요" className="p-5">
            <div className="flex flex-col gap-4">
              <p>{loadError}</p>
              <Button variant="secondary" onClick={() => setReloadKey((value) => value + 1)}>
                다시 시도
              </Button>
            </div>
          </Card>
        ) : !overviews ? (
          <div
            role="status"
            aria-label="복용약 불러오는 중"
            className="min-h-44 animate-pulse rounded-card bg-muted-bg"
          />
        ) : overviews.length === 0 ? (
          <Card title="이 기간에 등록한 처방이 없어요" className="p-5">
            <div className="flex flex-col gap-4">
              <p>다른 기간을 선택해 처방 기록을 확인해보세요.</p>
              <Button variant="secondary" onClick={() => setFilterOpen(true)}>
                기간 넓히기
              </Button>
            </div>
          </Card>
        ) : feature252 ? (
          <>
            <section className="flex flex-col gap-3" aria-labelledby="active-episode-list-title">
              <div className="flex items-baseline justify-between gap-3">
                <h2 id="active-episode-list-title" className="text-xl font-bold text-foreground">
                  복용 중
                </h2>
                <span className="text-sm text-muted-foreground tnum">{activeOverviews.length}개</span>
              </div>
              {activeOverviews.map(renderEpisodeCard)}
            </section>
            {finishedOverviews.length > 0 && (
              <section className="flex flex-col gap-3" aria-labelledby="finished-episode-list-title">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 id="finished-episode-list-title" className="text-xl font-bold text-foreground">
                    완료된 처방
                  </h2>
                  <span className="text-sm text-muted-foreground tnum">{finishedOverviews.length}개</span>
                </div>
                {finishedOverviews.map(renderEpisodeCard)}
              </section>
            )}
          </>
        ) : (
          <section className="flex flex-col gap-3" aria-labelledby="episode-list-title">
            <div className="flex items-baseline justify-between gap-3">
              <h2 id="episode-list-title" className="text-xl font-bold text-foreground">
                처방 기록
              </h2>
              <span className="text-sm text-muted-foreground tnum">{overviews.length}개</span>
            </div>
            {overviews.map(renderEpisodeCard)}
          </section>
        )}
      </main>

      <BottomTabbar
        active="medication"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
      <MedicationPeriodFilterSheet
        open={filterOpen}
        range={range}
        onOpenChange={setFilterOpen}
        onApply={(nextRange) => {
          const next = new URLSearchParams();
          if (nextRange.from) next.set('from', nextRange.from);
          if (nextRange.to) next.set('to', nextRange.to);
          setSearchParams(next);
          setFilterOpen(false);
        }}
      />
      <MedicationSlotSheet
        open={editing !== null}
        medication={editing?.medication ?? null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
        onSave={saveMedicationSlots}
      />
      <MedicationEpisodeSheet
        overview={episodeEditing}
        alias={episodeAlias}
        slots={episodeSlots}
        onAliasChange={setEpisodeAlias}
        onToggleSlot={toggleEpisodeSlot}
        onOpenChange={(open) => {
          if (!open) setEpisodeEditing(null);
        }}
        saving={episodeSaving}
        onSave={() => void saveEpisode()}
      />
      <MedicationBulkDeleteDialog
        open={deleteOpen}
        count={deleteTargets.length}
        pending={deletePending}
        error={deleteError}
        onOpenChange={(open) => {
          setDeleteOpen(open);
          if (!open) setDeleteError(null);
        }}
        onConfirm={() => void deleteSelectedMedications(deleteTargets)}
        onRetry={() => void deleteSelectedMedications(deleteTargets)}
      />
      <ErrorDialog
        open={saveError !== null}
        title="복용 시간을 저장하지 못했어요"
        message={saveError ?? ''}
        retryLabel="확인"
        onRetry={() => setSaveError(null)}
      />
    </div>
  );
}

interface MedicationEpisodeSheetProps {
  overview: MedicationOverview | null;
  alias: string;
  slots: Record<number, MealSlot[]>;
  onAliasChange: (value: string) => void;
  onToggleSlot: (medicationId: number, slot: MealSlot) => void;
  onOpenChange: (open: boolean) => void;
  saving: boolean;
  onSave: () => void;
}

function MedicationEpisodeSheet({
  overview,
  alias,
  slots,
  onAliasChange,
  onToggleSlot,
  onOpenChange,
  saving,
  onSave,
}: MedicationEpisodeSheetProps) {
  const readOnly = overview?.isFinished ?? false;
  return (
    <Dialog open={overview !== null} onOpenChange={onOpenChange}>
      <DialogContent variant="sheet" className="max-h-[88dvh] overflow-y-auto">
        {readOnly ? (
          <>
            <DialogHeader>
              <DialogTitle>완료된 처방</DialogTitle>
              <DialogDescription>완료된 처방의 복약 정보만 확인할 수 있어요.</DialogDescription>
            </DialogHeader>
            {overview && (
              <div className="flex flex-col gap-4" aria-label="완료된 처방 정보">
                <span className="self-start rounded-pill bg-muted-bg px-3 py-1.5 text-sm font-bold text-muted-foreground">
                  복용 완료
                </span>
                <div className="rounded-card border border-border bg-card p-4">
                  <p className="text-lg font-bold text-foreground">
                    {alias.trim() || `${formatDateLabel(overview.start.date, { includeYear: true })} 처방`}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground tnum">
                    {formatDatePeriod(overview.start.date, overview.endDate, { includeYear: true })}
                  </p>
                </div>
                <div className="flex flex-col gap-3">
                  {overview.medications.map((medication) => (
                    <div
                      key={medication.medicationId}
                      className="rounded-card border border-border bg-card p-4"
                    >
                      <p className="font-bold text-foreground">
                        {medication.name}{' '}
                        <span className="font-normal text-muted-foreground">{medication.dose}</span>
                      </p>
                      {medication.asNeeded ? (
                        <p className="mt-2 text-sm text-muted-foreground">필요할 때만 · 알림 없음</p>
                      ) : (
                        <p className="mt-2 text-sm text-muted-foreground">
                          {medication.slots.length > 0
                            ? medication.slots
                                .map(
                                  (slot) =>
                                    `${mealSlotLabel(slot, 'label')} ${overview.mealTimes[slot]}`,
                                )
                                .join(' · ')
                            : '복용 시간이 없어요.'}
                        </p>
                      )}
                      {medication.untilComplete && (
                        <p className="mt-2 text-sm font-bold text-warning-strong">처방 끝까지 복용</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>처방 편집</DialogTitle>
              <DialogDescription>약마다 복용 시간을 따로 골라요.</DialogDescription>
            </DialogHeader>
            {overview && (
              <div className="flex flex-col gap-4">
                <span className="self-start rounded-pill bg-primary-bg px-3 py-1.5 text-sm font-bold text-primary-strong">
                  복용 중
                </span>
                <Input
                  label="복약 별칭"
                  aria-label="복약 별칭"
                  placeholder="예: 감기약"
                  maxLength={50}
                  value={alias}
                  onChange={(event) => onAliasChange(event.target.value)}
                />
                <div className="flex flex-col gap-3">
                  {overview.medications.map((medication) => (
                    <div
                      key={medication.medicationId}
                      className="rounded-card border border-border bg-card p-3"
                    >
                      <p className="font-bold text-foreground">
                        {medication.name}{' '}
                        <span className="font-normal text-muted-foreground">{medication.dose}</span>
                      </p>
                      {medication.asNeeded ? (
                        <p className="mt-2 text-sm text-muted-foreground">필요할 때만 · 알림 없음</p>
                      ) : (
                        <div className="mt-3 grid grid-cols-4 gap-2">
                          {MEAL_SLOTS.map((slot) => {
                            const selected = (slots[medication.medicationId] ?? []).includes(slot.value);
                            return (
                              <button
                                key={slot.value}
                                type="button"
                                aria-pressed={selected}
                                aria-label={`${medication.name} ${slot.label}`}
                                onClick={() => onToggleSlot(medication.medicationId, slot.value)}
                                className={cn(
                                  'min-h-touch rounded-input border text-sm',
                                  selected
                                    ? 'border-primary bg-primary font-bold text-card'
                                    : 'border-border bg-card text-muted-foreground',
                                )}
                              >
                                {slot.short}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <DialogFooter>
              <Button disabled={saving} onClick={onSave}>
                {saving ? '저장 중...' : '저장'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
