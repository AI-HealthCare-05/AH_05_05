import { useEffect, useMemo, useState } from 'react';
import { Filter, Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import {
  cancelMedication,
  getMedicationDocumentImageUrl,
  getMedicationOverviews,
  releaseMedicationDocumentImageUrl,
  saveMedicationSchedule,
  type MealSlot,
  type MedicationOverview,
  type MedicationOverviewItem,
  type MedicationOverviewRange,
} from '@/entities/medication';
import {
  BottomTabbar,
  Button,
  Card,
  ErrorDialog,
  Header,
  ImageViewer,
  type TabKey,
} from '@/shared/ui';
import { MedicationBulkDeleteDialog } from './MedicationBulkDeleteDialog';
import { MedicationEpisodeCard } from './MedicationEpisodeCard';
import { MedicationPeriodFilterSheet } from './MedicationPeriodFilterSheet';
import { MedicationSlotSheet } from './MedicationSlotSheet';
import { medicationPeriodLabel, medicationRangeFromSearchParams } from './medicationPeriod';

const TAB_ROUTES: Record<TabKey, string> = {
  home: '/home',
  medication: '/medications',
  supplement: '/supplements',
  chat: '/chat',
  my: '/my',
};

interface MedicationsPageProps {
  overviewsLoader?: (range?: MedicationOverviewRange) => Promise<MedicationOverview[]>;
  medicationCanceller?: (recordId: number) => Promise<void>;
  documentImageLoader?: (documentImageUrl: string) => Promise<string>;
}

interface EditingMedication {
  recordId: number;
  medication: MedicationOverviewItem;
}

export function MedicationsPage({
  overviewsLoader = getMedicationOverviews,
  medicationCanceller = cancelMedication,
  documentImageLoader = getMedicationDocumentImageUrl,
}: MedicationsPageProps) {
  const navigate = useNavigate();
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
  const [saveError, setSaveError] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteTargets, setDeleteTargets] = useState<number[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    setOverviews(null);
    overviewsLoader(range)
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
  }, [overviewsLoader, range, reloadKey]);

  useEffect(
    () => () => {
      if (imageUrl) releaseMedicationDocumentImageUrl(imageUrl);
    },
    [imageUrl],
  );

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

  async function openDocumentImage(documentImageUrl: string) {
    setImageError(null);
    try {
      setImageUrl(await documentImageLoader(documentImageUrl));
    } catch (error: unknown) {
      setImageError(error instanceof Error ? error.message : '약봉투 사진을 불러오지 못했어요.');
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
        <button
          type="button"
          className="flex min-h-touch w-fit max-w-full items-center gap-2 rounded-pill border border-border bg-card px-4 text-sm font-bold text-foreground shadow-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setFilterOpen(true)}
        >
          <Filter aria-hidden className="size-4 shrink-0 text-primary" />
          {periodLabel}
        </button>

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
        ) : (
          <section className="flex flex-col gap-3" aria-labelledby="episode-list-title">
            <div className="flex items-baseline justify-between gap-3">
              <h2 id="episode-list-title" className="text-xl font-bold text-foreground">
                처방 기록
              </h2>
              <span className="text-sm text-muted-foreground tnum">{overviews.length}개</span>
            </div>
            {overviews.map((overview) => (
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
                onViewImage={() => void openDocumentImage(overview.documentImageUrl)}
              />
            ))}
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
      <ImageViewer
        open={imageUrl !== null}
        src={imageUrl ?? ''}
        title="약봉투 사진"
        onOpenChange={(open) => {
          if (!open) setImageUrl(null);
        }}
      />
      <ErrorDialog
        open={saveError !== null}
        title="복용 시간을 저장하지 못했어요"
        message={saveError ?? ''}
        retryLabel="확인"
        onRetry={() => setSaveError(null)}
      />
      <ErrorDialog
        open={imageError !== null}
        title="약봉투 사진을 불러오지 못했어요"
        message={imageError ?? ''}
        retryLabel="확인"
        onRetry={() => setImageError(null)}
      />
    </div>
  );
}
