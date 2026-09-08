import { useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import {
  listMedicationNotes,
  type MedicationNote,
  type MedicationNotePage,
} from '@/entities/medication-note';
import { useSession } from '@/app/SessionContext';
import { formatDateLabel } from '@/shared/lib/dateLabel';
import { BottomTabbar, Button, Card, Header } from '@/shared/ui';
import { TAB_ROUTES } from '@/shared/config/tabRoutes';

function noteDateLabel(value: string): string {
  const date = value.slice(0, 10);
  const time = value.slice(11, 16);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return value;
  return `${formatDateLabel(date)} ${time}`;
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
  const episodeIdParam = searchParams.get('episodeId');
  const parsedEpisodeId = episodeIdParam === null ? undefined : Number(episodeIdParam);
  const episodeId =
    parsedEpisodeId !== undefined && Number.isSafeInteger(parsedEpisodeId) && parsedEpisodeId > 0
      ? parsedEpisodeId
      : undefined;
  const requestGenerationRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const requestGeneration = requestGenerationRef.current + 1;
    requestGenerationRef.current = requestGeneration;
    setPage(null);
    setInitialLoadError(null);
    setLoadMoreError(null);
    setLoadingMore(false);
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

  function prescriptionLabel(note: MedicationNote): string {
    if (note.careEpisodeAlias) return note.careEpisodeAlias;
    if (note.careEpisodeStartDate) {
      return `${formatDateLabel(note.careEpisodeStartDate, { includeYear: true })} 처방`;
    }
    return `처방 #${note.careEpisodeId}`;
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
        <Button
          className="self-start"
          fullWidth={false}
          onClick={() => navigate('/medications/notes/new')}
        >
          <Plus aria-hidden className="mr-1 size-4" />
          새 메모 작성
        </Button>

        <section className="flex flex-col gap-3" aria-labelledby="medication-notes-title">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="medication-notes-title" aria-label={notesHeading} className="text-xl font-bold text-foreground">
                {notesHeading}
              </h2>
              {episodeId !== undefined && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {page?.items[0]
                    ? `${prescriptionLabel(page.items[0])} 메모만 보고 있어요.`
                    : '선택한 처방 메모만 보고 있어요.'}
                </p>
              )}
            </div>
            {episodeId !== undefined && (
              <Button
                variant="secondary"
                fullWidth={false}
                onClick={() => setSearchParams({})}
              >
                전체 메모 보기
              </Button>
            )}
          </div>
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
                  <button
                    type="button"
                    className="min-h-touch w-full break-words border-t border-border px-4 py-2 text-left text-sm font-bold text-primary-strong transition-colors hover:bg-primary-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                    onClick={() => setSearchParams({ episodeId: String(note.careEpisodeId) })}
                  >
                    {prescriptionLabel(note)} 메모만 보기
                  </button>
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
            </div>
          )}
        </section>
      </main>
      <BottomTabbar
        active="medication"
        onChange={(key) => navigate(TAB_ROUTES[key])}
        className="border-t border-border"
      />
    </div>
  );
}
