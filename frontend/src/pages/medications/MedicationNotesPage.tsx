import { useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import {
  deleteMedicationNote,
  listMedicationNoteEpisodes,
  listMedicationNotes,
  type MedicationNote,
  type MedicationNoteEpisode,
  type MedicationNotePage,
} from '@/entities/medication-note';
import { useSession } from '@/app/SessionContext';
import { formatDateLabel } from '@/shared/lib/dateLabel';
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
  Header,
} from '@/shared/ui';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';

function noteDateLabel(value: string): string {
  const date = value.slice(0, 10);
  const time = value.slice(11, 16);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return value;
  return `${formatDateLabel(date)} ${time}`;
}

function filterEpisodeBaseLabel(episode: MedicationNoteEpisode): string {
  if (episode.alias && episode.startDate) {
    return `${episode.alias} · ${formatDateLabel(episode.startDate, { includeYear: true })}`;
  }
  if (episode.alias) return episode.alias;
  if (episode.startDate) {
    return `${formatDateLabel(episode.startDate, { includeYear: true })} 처방`;
  }
  return `처방 #${episode.careEpisodeId}`;
}

export function MedicationNotesPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { principalKey } = useSession();
  const [page, setPage] = useState<MedicationNotePage | null>(null);
  const [initialLoadError, setInitialLoadError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [episodeOptions, setEpisodeOptions] = useState<MedicationNoteEpisode[] | null>(null);
  const [episodeOptionsError, setEpisodeOptionsError] = useState<string | null>(null);
  const [episodeOptionsRetryKey, setEpisodeOptionsRetryKey] = useState(0);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedNoteIds, setSelectedNoteIds] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteTargets, setDeleteTargets] = useState<number[]>([]);
  const episodeIdParam = searchParams.get('episodeId');
  const parsedEpisodeId = episodeIdParam === null ? undefined : Number(episodeIdParam);
  const episodeId =
    parsedEpisodeId !== undefined && Number.isSafeInteger(parsedEpisodeId) && parsedEpisodeId > 0
      ? parsedEpisodeId
      : undefined;
  const requestGenerationRef = useRef(0);
  const optionRequestGenerationRef = useRef(0);
  const deleteGenerationRef = useRef(0);
  const deletePendingRef = useRef(false);
  const principalKeyRef = useRef(principalKey);
  principalKeyRef.current = principalKey;

  useEffect(() => {
    let cancelled = false;
    const requestPrincipal = principalKey;
    const requestGeneration = optionRequestGenerationRef.current + 1;
    optionRequestGenerationRef.current = requestGeneration;
    setEpisodeOptions(null);
    setEpisodeOptionsError(null);
    listMedicationNoteEpisodes()
      .then((options) => {
        if (
          cancelled ||
          optionRequestGenerationRef.current !== requestGeneration ||
          principalKeyRef.current !== requestPrincipal
        ) return;
        setEpisodeOptions(options);
      })
      .catch(() => {
        if (
          !cancelled &&
          optionRequestGenerationRef.current === requestGeneration &&
          principalKeyRef.current === requestPrincipal
        ) {
          setEpisodeOptionsError('필터용 처방 목록을 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
      if (optionRequestGenerationRef.current === requestGeneration) {
        optionRequestGenerationRef.current += 1;
      }
    };
  }, [episodeOptionsRetryKey, principalKey]);

  useEffect(() => {
    let cancelled = false;
    const requestGeneration = requestGenerationRef.current + 1;
    requestGenerationRef.current = requestGeneration;
    const deleteGeneration = deleteGenerationRef.current + 1;
    deleteGenerationRef.current = deleteGeneration;
    deletePendingRef.current = false;
    setPage(null);
    setInitialLoadError(null);
    setLoadMoreError(null);
    setLoadingMore(false);
    setSelectionMode(false);
    setSelectedNoteIds(new Set());
    setDeleteOpen(false);
    setDeletePending(false);
    setDeleteError(null);
    setDeleteTargets([]);
    listMedicationNotes({ episodeId })
      .then((nextPage) => {
        if (cancelled || requestGenerationRef.current !== requestGeneration) return;
        setPage(nextPage);
      })
      .catch((error: unknown) => {
        if (!cancelled && requestGenerationRef.current === requestGeneration) {
          setInitialLoadError(error instanceof Error ? error.message : '복약 메모를 불러오지 못했어요.');
        }
      });
    return () => {
      cancelled = true;
      if (requestGenerationRef.current === requestGeneration) {
        requestGenerationRef.current += 1;
      }
      if (deleteGenerationRef.current === deleteGeneration) {
        deleteGenerationRef.current += 1;
      }
      deletePendingRef.current = false;
    };
  }, [episodeId, principalKey, retryKey]);

  async function loadMore() {
    if (!page?.nextCursor || loadingMore) return;
    const requestGeneration = requestGenerationRef.current;
    const requestedCursor = page.nextCursor;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const nextPage = await listMedicationNotes({ episodeId, cursor: requestedCursor });
      if (requestGenerationRef.current !== requestGeneration) return;
      setPage((current) => {
        if (!current) return nextPage;
        const existingIds = new Set(current.items.map((note) => note.id));
        return {
          items: [...current.items, ...nextPage.items.filter((note) => !existingIds.has(note.id))],
          total: nextPage.total,
          nextCursor: nextPage.nextCursor,
        };
      });
    } catch (error: unknown) {
      if (requestGenerationRef.current !== requestGeneration) return;
      setLoadMoreError(error instanceof Error ? error.message : '복약 메모를 더 불러오지 못했어요.');
    } finally {
      if (requestGenerationRef.current === requestGeneration) setLoadingMore(false);
    }
  }

  const notes = page?.items ?? [];
  const notesHeading = page ? `복약 메모 ${page.total}개` : '복약 메모 목록';
  const optionBaseLabels = episodeOptions?.map(filterEpisodeBaseLabel) ?? [];
  const optionLabelCounts = new Map<string, number>();
  for (const label of optionBaseLabels) {
    optionLabelCounts.set(label, (optionLabelCounts.get(label) ?? 0) + 1);
  }
  const selectedEpisodeIsMissing = episodeId !== undefined &&
    episodeOptions !== null &&
    !episodeOptions.some((episode) => episode.careEpisodeId === episodeId);

  function leaveSelectionMode() {
    if (deletePendingRef.current) return;
    setSelectionMode(false);
    setSelectedNoteIds(new Set());
    setDeleteOpen(false);
    setDeleteError(null);
    setDeleteTargets([]);
  }

  function toggleSelected(noteId: number) {
    setSelectedNoteIds((current) => {
      const next = new Set(current);
      if (next.has(noteId)) next.delete(noteId);
      else next.add(noteId);
      return next;
    });
  }

  function openDeleteConfirmation() {
    const targets = notes.filter((note) => selectedNoteIds.has(note.id)).map((note) => note.id);
    if (targets.length === 0) return;
    setDeleteTargets(targets);
    setDeleteError(null);
    setDeleteOpen(true);
  }

  async function deleteSelectedNotes(noteIds: number[]) {
    if (deletePendingRef.current || noteIds.length === 0) return;
    const mutationPrincipal = principalKey;
    const mutationGeneration = deleteGenerationRef.current;
    deletePendingRef.current = true;
    setDeletePending(true);
    setDeleteError(null);
    const succeeded: number[] = [];
    const failed: number[] = [];

    for (const noteId of noteIds) {
      if (
        deleteGenerationRef.current !== mutationGeneration ||
        principalKeyRef.current !== mutationPrincipal
      ) return;
      try {
        await deleteMedicationNote(String(noteId));
        if (
          deleteGenerationRef.current !== mutationGeneration ||
          principalKeyRef.current !== mutationPrincipal
        ) return;
        succeeded.push(noteId);
      } catch {
        if (
          deleteGenerationRef.current !== mutationGeneration ||
          principalKeyRef.current !== mutationPrincipal
        ) return;
        failed.push(noteId);
      }
    }

    if (
      deleteGenerationRef.current !== mutationGeneration ||
      principalKeyRef.current !== mutationPrincipal
    ) return;

    if (succeeded.length > 0) {
      const succeededIds = new Set(succeeded);
      setPage((current) => current && ({
        ...current,
        items: current.items.filter((note) => !succeededIds.has(note.id)),
        total: Math.max(0, current.total - succeeded.length),
      }));
    }

    if (failed.length === 0) {
      setDeleteOpen(false);
      setSelectionMode(false);
      setSelectedNoteIds(new Set());
      setDeleteTargets([]);
      toast.success(`${succeeded.length}개를 삭제했어요`);
    } else if (succeeded.length > 0) {
      setDeleteOpen(false);
      setSelectedNoteIds(new Set(failed));
      setDeleteTargets(failed);
      toast.warning(`${succeeded.length}개를 삭제했어요. ${failed.length}개는 실패했어요`);
    } else {
      setSelectedNoteIds(new Set(failed));
      setDeleteTargets(failed);
      setDeleteError('선택한 복약 메모를 삭제하지 못했어요. 다시 시도해주세요.');
    }
    deletePendingRef.current = false;
    setDeletePending(false);
  }

  function prescriptionLabel(note: MedicationNote): string {
    if (note.careEpisodeAlias) return note.careEpisodeAlias;
    if (note.careEpisodeStartDate) {
      return `${formatDateLabel(note.careEpisodeStartDate, { includeYear: true })} 처방`;
    }
    return `처방 #${note.careEpisodeId}`;
  }

  function setEpisodeFilter(value: string) {
    if (value === '') setSearchParams({});
    else setSearchParams({ episodeId: value });
  }

  function medicineLabel(note: MedicationNote): string {
    if (note.medicationId === null) return '처방 전체';
    return note.medication
      ? `${note.medication.name} ${note.medication.dose ?? ''}`.trim()
      : '삭제된 약';
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="복약 메모" onBack={() => navigate('/medications')} />
      <main className="flex flex-1 flex-col gap-5 overflow-y-auto px-page-x py-5">
        <div className="flex items-center justify-between gap-2">
          <Button
            className="self-start"
            fullWidth={false}
            onClick={() => navigate('/medications/notes/new')}
            disabled={selectionMode}
          >
            <Plus aria-hidden className="mr-1 size-4" />
            새 메모 작성
          </Button>
          <button
            type="button"
            className="min-h-touch px-2 text-sm font-bold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:text-disabled-foreground"
            onClick={() => selectionMode ? leaveSelectionMode() : setSelectionMode(true)}
            disabled={deletePending}
          >
            {selectionMode ? '완료' : '삭제'}
          </button>
        </div>

        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm font-bold text-foreground">
            처방
            <select
              aria-label="처방별 메모 필터"
              value={episodeId === undefined ? '' : String(episodeId)}
              onChange={(event) => setEpisodeFilter(event.target.value)}
              disabled={episodeOptions === null || selectionMode || deletePending}
              className="h-control w-full rounded-input border border-input bg-card px-3.5 text-[length:var(--text-control)] font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:bg-muted-bg disabled:text-disabled-foreground"
            >
              {episodeOptions === null ? (
                <option value={episodeId === undefined ? '' : String(episodeId)}>
                  {episodeOptionsError ? '처방 목록 확인 필요' : '처방 목록 불러오는 중'}
                </option>
              ) : (
                <>
                  <option value="">전체</option>
                  {episodeOptions.map((episode, index) => {
                    const baseLabel = optionBaseLabels[index];
                    const label = optionLabelCounts.get(baseLabel) === 1
                      ? baseLabel
                      : `${baseLabel} · #${episode.careEpisodeId}`;
                    return (
                      <option key={episode.careEpisodeId} value={episode.careEpisodeId}>
                        {label}
                      </option>
                    );
                  })}
                  {selectedEpisodeIsMissing && (
                    <option value={episodeId}>처방 #{episodeId}</option>
                  )}
                </>
              )}
            </select>
          </label>
          {episodeOptionsError && (
            <div className="flex flex-wrap items-center gap-2">
              <p role="alert" className="text-sm text-danger-strong">{episodeOptionsError}</p>
              <Button
                variant="secondary"
                fullWidth={false}
                onClick={() => setEpisodeOptionsRetryKey((current) => current + 1)}
              >
                처방 목록 다시 시도
              </Button>
            </div>
          )}
        </div>

        <section className="flex flex-col gap-3" aria-labelledby="medication-notes-title">
          <h2 id="medication-notes-title" aria-label={notesHeading} className="text-xl font-bold text-foreground">
            {notesHeading}
          </h2>
          {initialLoadError ? (
            <div className="flex flex-col items-start gap-3">
              <p role="alert" className="text-sm text-danger-strong">{initialLoadError}</p>
              <Button
                variant="secondary"
                fullWidth={false}
                onClick={() => setRetryKey((current) => current + 1)}
              >
                다시 시도
              </Button>
            </div>
          ) : page === null ? (
            <div role="status" aria-label="복약 메모 불러오는 중" className="min-h-32 animate-pulse rounded-card bg-muted-bg" />
          ) : notes.length === 0 ? (
            <Card className="p-5">
              <p>복용 후 느낀 점을 남겨두면 다음 진료 때 도움이 돼요.</p>
            </Card>
          ) : (
            <div className="flex flex-col gap-3">
              {notes.map((note) => (
                <article
                  key={note.id}
                  className="overflow-hidden rounded-card bg-card shadow-card"
                >
                  {selectionMode ? (
                    <label className="flex min-h-28 w-full cursor-pointer items-start gap-3 p-4 text-left transition-colors hover:bg-muted-bg">
                      <input
                        type="checkbox"
                        aria-label={`메모 선택: ${note.id}`}
                        checked={selectedNoteIds.has(note.id)}
                        onChange={() => toggleSelected(note.id)}
                        disabled={deletePending}
                        className="mt-1 size-5 shrink-0 accent-primary"
                      />
                      <span className="flex min-w-0 flex-1 flex-col gap-2">
                        <span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                          <span className="tnum">{noteDateLabel(note.dosedAt)}</span>
                          <span className="min-w-0 max-w-full break-words rounded-pill bg-primary-bg px-2.5 py-1 font-bold text-primary-strong">
                            {prescriptionLabel(note)}
                          </span>
                        </span>
                        <span className="font-bold text-foreground">{medicineLabel(note)}</span>
                        <span className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{note.body}</span>
                      </span>
                    </label>
                  ) : (
                    <button
                      type="button"
                      aria-label={`${medicineLabel(note)} ${note.body}`}
                      className="flex min-h-28 w-full flex-col gap-2 p-4 text-left transition-colors hover:bg-muted-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                      onClick={() => navigate(`/medications/notes/${encodeURIComponent(note.id)}`)}
                    >
                      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                        <span className="tnum">{noteDateLabel(note.dosedAt)}</span>
                        <span className="min-w-0 max-w-full break-words rounded-pill bg-primary-bg px-2.5 py-1 font-bold text-primary-strong">
                          {prescriptionLabel(note)}
                        </span>
                      </div>
                      <p className="font-bold text-foreground">{medicineLabel(note)}</p>
                      <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{note.body}</p>
                    </button>
                  )}
                </article>
              ))}
              {loadMoreError && (
                <p role="alert" className="text-sm text-danger-strong">{loadMoreError}</p>
              )}
              {page.nextCursor && (
                <Button
                  variant="secondary"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  aria-busy={loadingMore}
                >
                  {loadingMore ? '불러오는 중...' : '더 보기'}
                </Button>
              )}
              {selectionMode && (
                <Button
                  variant="danger"
                  disabled={selectedNoteIds.size === 0 || deletePending}
                  onClick={openDeleteConfirmation}
                >
                  선택한 {selectedNoteIds.size}개 삭제
                </Button>
              )}
            </div>
          )}
        </section>
      </main>
      <BottomTabbar
        active="medication"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
      <Dialog
        open={deleteOpen}
        onOpenChange={(open) => {
          if (deletePending) return;
          setDeleteOpen(open);
          if (!open) setDeleteError(null);
        }}
      >
        <DialogContent variant="sheet">
          <DialogHeader>
            <DialogTitle>선택한 복약 메모를 삭제할까요?</DialogTitle>
            <DialogDescription>
              {deleteTargets.length}개의 메모가 삭제되며 다시 볼 수 없어요.
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p role="alert" className="text-sm text-danger-strong">{deleteError}</p>}
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteOpen(false)} disabled={deletePending}>
              취소
            </Button>
            <Button
              variant="danger"
              onClick={() => void deleteSelectedNotes(deleteTargets)}
              disabled={deletePending}
            >
              {deletePending ? '삭제 중...' : deleteError ? '다시 시도' : '삭제하기'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
